"""Consulta determinística da vitrine publicável do CineViva."""

import sqlite3
from datetime import datetime, timezone

from .catalog_policy import (
    evaluate_catalog_visibility,
    rank_catalog_movies,
)


TMDB_POSTER_BASE_URL = "https://image.tmdb.org/t/p/w500"


def list_public_catalog(
    connection: sqlite3.Connection,
    *,
    now: datetime | None = None,
    limit: int = 20,
    only_bookable: bool = False,
) -> list[dict]:
    """Retorna a coleta BR mais recente filtrada pela política do produto."""
    if now is None:
        now = datetime.now(timezone.utc)

    if (
        not isinstance(now, datetime)
        or now.tzinfo is None
        or now.utcoffset() is None
    ):
        raise ValueError("now deve ser um datetime com fuso horário.")

    if type(limit) is not int or limit <= 0:
        raise ValueError("limit deve ser um inteiro positivo.")

    if type(only_bookable) is not bool:
        raise ValueError("only_bookable deve ser booleano.")

    now = now.astimezone(timezone.utc)
    now_epoch = int(now.timestamp())

    collection = connection.execute(
        """
        SELECT collection_id, collected_at, finished_at
        FROM catalog_collections
        WHERE provider = 'tmdb' AND region = 'BR'
        ORDER BY finished_at DESC, collected_at DESC, collection_id DESC
        LIMIT 1
        """
    ).fetchone()

    if collection is None:
        return []

    collection_finished_at = datetime.fromtimestamp(
        collection["finished_at"],
        tz=timezone.utc,
    )

    rows = connection.execute(
        """
        SELECT
            m.movie_id,
            m.title,
            m.synopsis,
            m.runtime_minutes,
            m.age_rating,
            m.poster_path,
            m.source_url,
            ccm.popularity,
            ccm.br_release_date,
            ccm.br_release_type,
            EXISTS (
                SELECT 1
                FROM sessions AS s
                WHERE s.movie_id = m.movie_id
                  AND s.status = 'SCHEDULED'
                  AND s.starts_at > ?
            ) AS has_future_sessions
        FROM catalog_collection_movies AS ccm
        JOIN movies AS m ON m.movie_id = ccm.movie_id
        WHERE ccm.collection_id = ?
        """,
        (now_epoch, collection["collection_id"]),
    ).fetchall()

    visible = []

    for row in rows:
        movie = dict(row)
        has_release = (
            movie["br_release_date"] is not None
            and movie["br_release_type"] in (2, 3)
        )
        has_future_sessions = bool(movie.pop("has_future_sessions"))

        visibility = evaluate_catalog_visibility(
            movie,
            in_latest_collection=True,
            has_br_theatrical_release=has_release,
            has_future_sessions=has_future_sessions,
            collection_finished_at=collection_finished_at,
            now=now,
        )

        if not visibility.show_in_catalog:
            continue

        if only_bookable and not visibility.show_session_options:
            continue

        genre_rows = connection.execute(
            """
            SELECT g.name
            FROM movie_genres AS mg
            JOIN genres AS g ON g.genre_id = mg.genre_id
            WHERE mg.movie_id = ?
            ORDER BY g.name COLLATE NOCASE, g.genre_id
            """,
            (movie["movie_id"],),
        ).fetchall()

        movie["genres"] = [genre["name"] for genre in genre_rows]
        movie["poster_url"] = (
            f"{TMDB_POSTER_BASE_URL}{movie['poster_path']}"
            if movie["poster_path"]
            else None
        )
        movie["show_session_options"] = (
            visibility.show_session_options
        )
        movie["catalog_collection_id"] = collection["collection_id"]
        movie["catalog_collected_at"] = datetime.fromtimestamp(
            collection["collected_at"],
            tz=timezone.utc,
        ).isoformat(timespec="seconds")

        visible.append(movie)

    return rank_catalog_movies(visible)[:limit]
