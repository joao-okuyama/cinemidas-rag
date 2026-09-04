"""Conexão e inicialização do banco SQLite do CineMidas v2."""

import sqlite3
from pathlib import Path


BOOKING_DIRECTORY = Path(__file__).resolve().parent


def connect_database(database_path: str | Path) -> sqlite3.Connection:
    """Abre uma conexão com integridade referencial habilitada.

    A pasta de destino deve existir.

    Quem chama esta função é responsável por fechar a conexão.
    """
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
) -> None:
    """Inicializa os esquemas e, opcionalmente, o catálogo fictício.

    Deve ser executada antes de iniciar operações de negócio.

    Os scripts SQL controlam suas próprias transações. Portanto,
    a inicialização completa não constitui uma transação única.

    Esta função não substitui um sistema de migrações.
    """
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

    # Lê todos os arquivos antes de executar qualquer script.
    scripts = [
        (
            script_name,
            (BOOKING_DIRECTORY / script_name).read_text(
                encoding="utf-8"
            ),
        )
        for script_name in script_names
    ]

    for script_name, script_content in scripts:
        try:
            connection.executescript(script_content)

        except sqlite3.Error as error:
            connection.rollback()

            raise RuntimeError(
                f"Falha ao executar o script {script_name}."
            ) from error

    foreign_key_violation = connection.execute(
        "PRAGMA foreign_key_check"
    ).fetchone()

    if foreign_key_violation is not None:
        raise RuntimeError(
            "Foram encontradas referências inválidas no banco."
        )
