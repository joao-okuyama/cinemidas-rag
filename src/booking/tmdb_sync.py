import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from .normalized_movie_repository import save_normalized_movies
from .tmdb_client import TMDBClient
from .tmdb_normalizer import normalize_tmdb_movie


class TMDBSyncError(RuntimeError):

    pass



@dataclass
class TMDBSyncResult:
    pages_fetched: int
    movies_processed: int
    duplicate_ids: int
    collected_at: str
    warnings: dict[str, tuple[str, ...]]


def sync_now_playing(
    connection: sqlite3.Connection,
    client: TMDBClient,
    *,
    max_pages: int = 20,
    max_movies: int = 500,
    collected_at: datetime | None = None,
) -> TMDBSyncResult:

    if connection.in_transaction:
        raise RuntimeError(
            "Finalize a transação atual antes de sincronizar o catálogo."
        )

    foreign_keys_enabled = connection.execute(
        "PRAGMA foreign_keys"
    ).fetchone()[0]

    if foreign_keys_enabled != 1:
        raise RuntimeError(
            "A sincronização exige integridade referencial habilitada."
        )

    if type(max_pages) is not int or max_pages <= 0:
        raise ValueError(
            "max_pages deve ser um inteiro positivo."
        )

    if type(max_movies) is not int or max_movies <= 0:
        raise ValueError(
            "max_movies deve ser um inteiro positivo."
        )

    if collected_at is None:
        collected_at = datetime.now(timezone.utc)

    if (
        not isinstance(collected_at, datetime)
        or collected_at.tzinfo is None
        or collected_at.utcoffset() is None
    ):
        raise ValueError(
            "collected_at deve ser um datetime com fuso horário."
        )

    collected_at = collected_at.astimezone(timezone.utc)

    # Confere a estrutura necessária antes das chamadas externas.
    connection.execute(
        "SELECT movie_id, poster_path FROM movies LIMIT 0"
    )
    connection.execute(
        "SELECT genre_id, name FROM genres LIMIT 0"
    )
    connection.execute(
        "SELECT movie_id, genre_id FROM movie_genres LIMIT 0"
    )

    first_page = client.get_now_playing_page(page=1)
    total_pages = first_page["total_pages"]

    if total_pages == 0:
        raise TMDBSyncError(
            "O TMDB retornou um catálogo vazio. "
            "Nenhuma alteração foi realizada."
        )

    if total_pages > max_pages:
        raise TMDBSyncError(
            f"O TMDB informou {total_pages} páginas, "
            f"acima do limite configurado de {max_pages}. "
            "Nenhuma alteração foi realizada."
        )

    # Dicionários preservam a ordem de inclusão dos IDs.
    movie_ids = {}
    duplicate_ids = 0
    pages_fetched = 0

    for page_number in range(1, total_pages + 1):
        if page_number == 1:
            page = first_page
        else:
            page = client.get_now_playing_page(page=page_number)

        if page["total_pages"] != total_pages:
            raise TMDBSyncError(
                "A quantidade de páginas mudou durante a coleta. "
                "Execute a sincronização novamente."
            )

        if not page["results"]:
            raise TMDBSyncError(
                f"A página {page_number} veio vazia. "
                "Nenhuma alteração foi realizada."
            )

        pages_fetched += 1

        for movie in page["results"]:
            movie_id = movie["id"]

            if movie_id in movie_ids:
                duplicate_ids += 1
                continue

            movie_ids[movie_id] = None

            if len(movie_ids) > max_movies:
                raise TMDBSyncError(
                    "A quantidade de filmes excedeu o limite "
                    f"configurado de {max_movies}. "
                    "Nenhuma alteração foi realizada."
                )

    normalized_movies = []
    warnings = {}

    for movie_id in movie_ids:
        details = client.get_movie_details(movie_id)

        normalized = normalize_tmdb_movie(
            details,
            collected_at=collected_at,
        )

        normalized_movies.append(normalized)

        if normalized.warnings:
            warnings[normalized.record["movie_id"]] = (
                normalized.warnings
            )

    processed = save_normalized_movies(
        connection,
        normalized_movies,
    )

    return TMDBSyncResult(
        pages_fetched=pages_fetched,
        movies_processed=processed,
        duplicate_ids=duplicate_ids,
        collected_at=collected_at.isoformat(timespec="seconds"),
        warnings=warnings,
    )
