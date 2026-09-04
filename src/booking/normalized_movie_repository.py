import math
import re
import sqlite3
from datetime import date

from .movie_catalog import _prepare_movie_records, _write_movie_records
from .tmdb_normalizer import NormalizedMovie, _genres, _poster_path


def _require_writable_connection(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        raise RuntimeError(
            "Finalize a transação atual antes de salvar filmes."
        )

    foreign_keys_enabled = connection.execute(
        "PRAGMA foreign_keys"
    ).fetchone()[0]

    if foreign_keys_enabled != 1:
        raise RuntimeError(
            "A gravação exige integridade referencial habilitada."
        )


def _prepare_normalized_batch(
    normalized_movies: list[NormalizedMovie],
) -> tuple[list[dict], list[tuple], dict[int, str]]:
    if not isinstance(normalized_movies, list) or not normalized_movies:
        raise ValueError(
            "Informe uma lista não vazia de filmes normalizados."
        )

    for item in normalized_movies:
        if not isinstance(item, NormalizedMovie):
            raise ValueError(
                "Todos os itens devem ser instâncias de NormalizedMovie."
            )

    movies = _prepare_movie_records(
        [item.record for item in normalized_movies]
    )
    presentations = []
    genre_names = {}

    for item, movie in zip(normalized_movies, movies):
        if movie["provider"] != "tmdb":
            raise ValueError(
                "Este fluxo aceita somente filmes normalizados do TMDB."
            )

        if type(item.poster_provided) is not bool:
            raise ValueError("poster_provided deve ser booleano.")

        if not item.poster_provided and item.poster_path is not None:
            raise ValueError(
                "Um pôster não informado não pode conter um caminho."
            )

        poster_payload = {}
        if item.poster_provided:
            poster_payload["poster_path"] = item.poster_path

        poster_provided, poster_path = _poster_path(poster_payload)

        if item.genres is None:
            genres = None
        else:
            if not isinstance(item.genres, tuple):
                raise ValueError(
                    "Os gêneros normalizados devem ser uma tupla ou nulo."
                )

            raw_genres = []
            for entry in item.genres:
                if not isinstance(entry, tuple) or len(entry) != 2:
                    raise ValueError(
                        "Cada gênero normalizado deve conter ID e nome."
                    )
                raw_genres.append({"id": entry[0], "name": entry[1]})

            genres = _genres({"genres": raw_genres})

            for genre_id, name in genres:
                if (
                    genre_id in genre_names
                    and genre_names[genre_id] != name
                ):
                    raise ValueError(
                        "O lote contém nomes divergentes para um mesmo gênero."
                    )
                genre_names[genre_id] = name

        presentations.append(
            (movie["movie_id"], poster_provided, poster_path, genres)
        )

    return movies, presentations, genre_names


def _write_normalized_batch(
    connection: sqlite3.Connection,
    movies: list[dict],
    presentations: list[tuple],
    genre_names: dict[int, str],
) -> None:
    _write_movie_records(connection, movies)

    connection.executemany(
        """
        INSERT INTO genres (genre_id, name)
        VALUES (?, ?)
        ON CONFLICT (genre_id) DO UPDATE SET name = excluded.name
        """,
        sorted(genre_names.items()),
    )

    for movie_id, poster_provided, poster_path, genres in presentations:
        if poster_provided:
            connection.execute(
                "UPDATE movies SET poster_path = ? WHERE movie_id = ?",
                (poster_path, movie_id),
            )

        if genres is not None:
            connection.execute(
                "DELETE FROM movie_genres WHERE movie_id = ?",
                (movie_id,),
            )
            connection.executemany(
                """
                INSERT INTO movie_genres (movie_id, genre_id)
                VALUES (?, ?)
                """,
                [(movie_id, genre_id) for genre_id, _ in genres],
            )


def _collection_evidence(
    normalized_movies: list[NormalizedMovie],
) -> list[tuple[str, float | None, str | None, int | None]]:
    evidence = []

    for item in normalized_movies:
        popularity = item.popularity
        if popularity is not None:
            if type(popularity) not in (int, float):
                raise ValueError("popularity deve ser numérica ou nula.")
            popularity = float(popularity)
            if not math.isfinite(popularity) or popularity < 0:
                raise ValueError("popularity deve ser finita e não negativa.")

        release_date = item.br_release_date
        release_type = item.br_release_type

        if (release_date is None) != (release_type is None):
            raise ValueError(
                "Data e tipo do lançamento brasileiro devem coexistir."
            )

        if release_date is not None:
            if (
                not isinstance(release_date, str)
                or re.fullmatch(r"\d{4}-\d{2}-\d{2}", release_date) is None
            ):
                raise ValueError("Data de lançamento brasileira inválida.")
            try:
                date.fromisoformat(release_date)
            except ValueError:
                raise ValueError(
                    "Data de lançamento brasileira inválida."
                ) from None
            if type(release_type) is not int or release_type not in (2, 3):
                raise ValueError("Tipo de lançamento brasileiro inválido.")

        evidence.append(
            (
                item.record["movie_id"],
                popularity,
                release_date,
                release_type,
            )
        )

    return evidence


def save_normalized_movies(
    connection: sqlite3.Connection,
    normalized_movies: list[NormalizedMovie],
) -> int:
    _require_writable_connection(connection)
    movies, presentations, genre_names = _prepare_normalized_batch(
        normalized_movies
    )

    try:
        connection.execute("BEGIN IMMEDIATE")
        _write_normalized_batch(
            connection, movies, presentations, genre_names
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise

    return len(movies)


def save_normalized_collection(
    connection: sqlite3.Connection,
    normalized_movies: list[NormalizedMovie],
    *,
    collection_id: str,
    collected_at: int,
    finished_at: int,
    pages_fetched: int,
    duplicate_ids: int,
) -> int:
    """Persiste filmes e evidências da coleta em uma única transação."""
    _require_writable_connection(connection)

    if not isinstance(collection_id, str) or not collection_id.strip():
        raise ValueError("collection_id é obrigatório.")

    integer_fields = {
        "collected_at": collected_at,
        "finished_at": finished_at,
        "pages_fetched": pages_fetched,
        "duplicate_ids": duplicate_ids,
    }
    for field_name, value in integer_fields.items():
        if type(value) is not int:
            raise ValueError(f"{field_name} deve ser inteiro.")

    if collected_at <= 0 or finished_at < collected_at:
        raise ValueError("Intervalo da coleta inválido.")
    if pages_fetched <= 0 or duplicate_ids < 0:
        raise ValueError("Contadores da coleta inválidos.")

    movies, presentations, genre_names = _prepare_normalized_batch(
        normalized_movies
    )
    evidence = _collection_evidence(normalized_movies)

    try:
        connection.execute("BEGIN IMMEDIATE")
        _write_normalized_batch(
            connection, movies, presentations, genre_names
        )
        connection.execute(
            """
            INSERT INTO catalog_collections (
                collection_id, provider, region, collected_at,
                finished_at, pages_fetched, movies_processed, duplicate_ids
            )
            VALUES (?, 'tmdb', 'BR', ?, ?, ?, ?, ?)
            """,
            (
                collection_id.strip(),
                collected_at,
                finished_at,
                pages_fetched,
                len(movies),
                duplicate_ids,
            ),
        )
        connection.executemany(
            """
            INSERT INTO catalog_collection_movies (
                collection_id, movie_id, popularity,
                br_release_date, br_release_type
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (collection_id.strip(), *movie_evidence)
                for movie_evidence in evidence
            ],
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise

    return len(movies)
