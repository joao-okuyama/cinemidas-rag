import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


MIGRATIONS_DIRECTORY = (
    Path(__file__).resolve().parent / "migrations"
)


def _execute_statements(
    connection: sqlite3.Connection,
    script: str,
) -> None:

    buffer = ""

    for character in script:
        buffer += character

        if character == ";" and sqlite3.complete_statement(buffer):
            connection.execute(buffer)
            buffer = ""

    # Permite comentários finais ou uma instrução sem ponto e vírgula.
    # SQL incompleto ou inválido provocará erro do SQLite.
    if buffer.strip():
        connection.execute(buffer)


def apply_migrations(
    connection: sqlite3.Connection,
    *,
    migrations_directory: str | Path | None = None,
) -> list[str]:
    """Aplica migrações pendentes e retorna seus nomes.

    Requer o esquema básico previamente inicializado.

    Cada arquivo segue o padrão 001_descricao.sql.
    Todas as migrações pendentes desta chamada são aplicadas
    na mesma transação.

    Arquivos já aplicados não podem ser alterados ou removidos:
    uma nova mudança exige uma nova migração.
    """
    if connection.in_transaction:
        raise RuntimeError(
            "Finalize a transação atual antes de aplicar migrações."
        )

    foreign_keys_enabled = connection.execute(
        "PRAGMA foreign_keys"
    ).fetchone()[0]

    if foreign_keys_enabled != 1:
        raise RuntimeError(
            "As migrações exigem integridade referencial habilitada."
        )

    directory = (
        Path(migrations_directory)
        if migrations_directory is not None
        else MIGRATIONS_DIRECTORY
    )

    if not directory.is_dir():
        raise FileNotFoundError(
            "O diretório de migrações não foi encontrado."
        )

    paths = sorted(directory.glob("[0-9][0-9][0-9]_*.sql"))

    migration_files = {}
    seen_versions = set()

    # Lê todos os arquivos antes de iniciar a transação.
    for path in paths:
        version = path.name[:3]

        if version in seen_versions:
            raise ValueError(
                f"Versão de migração duplicada: {version}."
            )

        seen_versions.add(version)

        script = path.read_text(encoding="utf-8-sig")
        checksum = hashlib.sha256(
            script.encode("utf-8")
        ).hexdigest()

        migration_files[path.name] = (script, checksum)

    applied_now = []

    try:
        connection.execute("BEGIN IMMEDIATE")

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_id TEXT PRIMARY KEY NOT NULL,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )

        applied_rows = connection.execute(
            """
            SELECT migration_id, checksum
            FROM schema_migrations
            ORDER BY migration_id
            """
        ).fetchall()

        applied = {
            row[0]: row[1]
            for row in applied_rows
        }

        for migration_id, saved_checksum in applied.items():
            if migration_id not in migration_files:
                raise RuntimeError(
                    "Arquivo de migração já aplicada está ausente: "
                    f"{migration_id}."
                )

            current_checksum = migration_files[migration_id][1]

            if current_checksum != saved_checksum:
                raise RuntimeError(
                    "Uma migração já aplicada foi alterada: "
                    f"{migration_id}. Crie uma nova migração."
                )

        latest_applied = max(applied, default="")

        for migration_id, (script, checksum) in migration_files.items():
            if migration_id in applied:
                continue

            if migration_id < latest_applied:
                raise RuntimeError(
                    "Foi encontrada uma migração pendente anterior "
                    f"às já aplicadas: {migration_id}."
                )

            _execute_statements(connection, script)

            connection.execute(
                """
                INSERT INTO schema_migrations (
                    migration_id,
                    checksum,
                    applied_at
                )
                VALUES (?, ?, ?)
                """,
                (
                    migration_id,
                    checksum,
                    datetime.now(timezone.utc).isoformat(
                        timespec="seconds"
                    ),
                ),
            )

            applied_now.append(migration_id)

        violation = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchone()

        if violation is not None:
            raise RuntimeError(
                "A migração deixou referências inválidas no banco."
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    return applied_now
