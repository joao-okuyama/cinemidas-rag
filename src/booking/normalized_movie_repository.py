import sqlite3

from .movie_catalog import (
    _prepare_movie_records,
    _write_movie_records,
)
from .tmdb_normalizer import (
    NormalizedMovie,
    _genres,
    _poster_path,
)


def save_normalized_movies(
    connection: sqlite3.Connection,
    normalized_movies: list[NormalizedMovie],
) -> int:

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

    if (
        not isinstance(normalized_movies, list)
        or not normalized_movies
    ):
        raise ValueError(
            "Informe uma lista não vazia de filmes normalizados."
        )

    for item in normalized_movies:
        if not isinstance(item, NormalizedMovie):
            raise ValueError(
                "Todos os itens devem ser instâncias de NormalizedMovie."
            )

    # Valida e copia os campos básicos antes de abrir a transação.
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
            raise ValueError(
                "poster_provided deve ser booleano."
            )

        if not item.poster_provided and item.poster_path is not None:
            raise ValueError(
                "Um pôster não informado não pode conter um caminho."
            )

        poster_payload = {}

        if item.poster_provided:
            poster_payload["poster_path"] = item.poster_path

        # Revalida os valores: NormalizedMovie pode ter sido modificado
        # depois de ser produzido pelo normalizador.
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

                raw_genres.append(
                    {
                        "id": entry[0],
                        "name": entry[1],
                    }
                )

            genres = _genres({"genres": raw_genres})

            for genre_id, name in genres:
                if (
                    genre_id in genre_names
                    and genre_names[genre_id] != name
                ):
                    raise ValueError(
                        "O lote contém nomes divergentes "
                        "para um mesmo gênero."
                    )

                genre_names[genre_id] = name

        presentations.append(
            (
                movie["movie_id"],
                poster_provided,
                poster_path,
                genres,
            )
        )

    try:
        connection.execute("BEGIN IMMEDIATE")

        # Esta função interna não executa commit.
        _write_movie_records(connection, movies)

        # Atualiza os nomes dos gêneros informados no lote.
        connection.executemany(
            """
            INSERT INTO genres (genre_id, name)
            VALUES (?, ?)
            ON CONFLICT (genre_id) DO UPDATE SET
                name = excluded.name
            """,
            sorted(genre_names.items()),
        )

        for (
            movie_id,
            poster_provided,
            poster_path,
            genres,
        ) in presentations:
            if poster_provided:
                connection.execute(
                    """
                    UPDATE movies
                    SET poster_path = ?
                    WHERE movie_id = ?
                    """,
                    (poster_path, movie_id),
                )

            if genres is not None:
                # Substitui apenas as associações deste filme.
                connection.execute(
                    """
                    DELETE FROM movie_genres
                    WHERE movie_id = ?
                    """,
                    (movie_id,),
                )

                connection.executemany(
                    """
                    INSERT INTO movie_genres (
                        movie_id,
                        genre_id
                    )
                    VALUES (?, ?)
                    """,
                    [
                        (movie_id, genre_id)
                        for genre_id, _ in genres
                    ],
                )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    return len(movies)
