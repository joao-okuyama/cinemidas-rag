import sqlite3
from pathlib import Path

from .migrations import apply_migrations


BOOKING_DIRECTORY = Path(__file__).resolve().parent


def connect_database(database_path: str | Path) -> sqlite3.Connection:

    connection = sqlite3.connect(
        str(database_path),
        timeout=5.0,
    )

    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")

        foreign_keys_enabled = connection.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0]

        if foreign_keys_enabled != 1:
            raise RuntimeError(
                "Não foi possível habilitar a integridade referencial."
            )

        return connection

    except Exception:
        connection.close()
        raise


def initialize_database(
    connection: sqlite3.Connection,
    *,
    seed_catalog: bool = False,
    migrate: bool = True,
) -> None:

    if connection.in_transaction:
        raise RuntimeError(
            "Finalize a transação atual antes de inicializar o banco."
        )

    connection.execute("PRAGMA foreign_keys = ON")

    foreign_keys_enabled = connection.execute(
        "PRAGMA foreign_keys"
    ).fetchone()[0]

    if foreign_keys_enabled != 1:
        raise RuntimeError(
            "A inicialização exige integridade referencial habilitada."
        )

    script_names = [
        "schema.sql",
        "session_schema.sql",
    ]

    if seed_catalog:
        script_names.append("seed_catalog.sql")

    scripts = {
        script_name: (
            BOOKING_DIRECTORY / script_name
        ).read_text(encoding="utf-8")
        for script_name in script_names
    }

    def execute_base_script(script_name: str) -> None:
        try:
            connection.executescript(scripts[script_name])

        except sqlite3.Error as error:
            connection.rollback()

            raise RuntimeError(
                f"Falha ao executar o script {script_name}."
            ) from error

    execute_base_script("schema.sql")
    execute_base_script("session_schema.sql")

    if migrate:
        apply_migrations(connection)

    if seed_catalog:
        execute_base_script("seed_catalog.sql")

    foreign_key_violation = connection.execute(
        "PRAGMA foreign_key_check"
    ).fetchone()

    if foreign_key_violation is not None:
        raise RuntimeError(
            "Foram encontradas referências inválidas no banco."
        )
