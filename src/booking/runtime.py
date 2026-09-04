"""Inicialização do banco e do catálogo usados pela aplicação web."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .database import connect_database, initialize_database
from .public_catalog import list_public_catalog
from .session_scheduler import generate_demo_sessions
from .tmdb_client import TMDBClient
from .tmdb_sync import sync_now_playing


@dataclass(frozen=True)
class RuntimeStatus:
    database_path: str
    catalog_movies: int
    catalog_synchronized: bool
    sessions_created: int


def prepare_booking_runtime(
    database_path: str | Path,
    *,
    tmdb_token: str | None,
    now: datetime | None = None,
) -> RuntimeStatus:
    """Cria a base local e atualiza o TMDB somente quando necessário."""
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect_database(path)

    try:
        initialize_database(connection, seed_catalog=True)
        movies = list_public_catalog(connection, now=now, limit=500)
        synchronized = False

        if not movies:
            if not isinstance(tmdb_token, str) or not tmdb_token.strip():
                raise RuntimeError(
                    "O catálogo precisa ser atualizado, mas "
                    "TMDB_API_TOKEN não foi configurado."
                )
            sync_now_playing(
                connection,
                TMDBClient(tmdb_token),
                collected_at=now,
            )
            synchronized = True
            movies = list_public_catalog(connection, now=now, limit=500)

        if not movies:
            raise RuntimeError(
                "A coleta atual não possui filmes publicáveis no Brasil."
            )

        schedule = generate_demo_sessions(connection, now=now)
        return RuntimeStatus(
            database_path=str(path),
            catalog_movies=len(movies),
            catalog_synchronized=synchronized,
            sessions_created=schedule.created_sessions,
        )
    finally:
        connection.close()
