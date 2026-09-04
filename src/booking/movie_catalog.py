import csv
import sqlite3
from pathlib import Path


CSV_COLUMNS = (
    "movie_id",
    "provider",
    "provider_movie_id",
    "title",
    "synopsis",
    "runtime_minutes",
    "age_rating",
    "source_url",
    "source_updated_at",
)


def read_movies_csv(csv_path: str | Path) -> list[dict]:
    movies = []
    seen_movie_ids = set()
    seen_external_ids = set()

    with Path(csv_path).open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        reader = csv.DictReader(csv_file)

        if reader.fieldnames != list(CSV_COLUMNS):
            raise ValueError(
                "Cabeçalho CSV inválido. Use exatamente: "
                + ",".join(CSV_COLUMNS)
            )

        for row in reader:
            line_number = reader.line_num

            if None in row or any(
                value is None for value in row.values()
            ):
                raise ValueError(
                    f"Linha {line_number}: quantidade de campos inválida."
                )

            movie = {
                column: row[column].strip() or None
                for column in CSV_COLUMNS
            }

            movie_id = movie["movie_id"]

            if not movie_id or not movie["title"]:
                raise ValueError(
                    f"Linha {line_number}: movie_id e title são obrigatórios."
                )

            if movie_id in seen_movie_ids:
                raise ValueError(
                    f"Linha {line_number}: movie_id duplicado no arquivo."
                )

            seen_movie_ids.add(movie_id)

            provider = movie["provider"]
            provider_movie_id = movie["provider_movie_id"]

            if (provider is None) != (provider_movie_id is None):
                raise ValueError(
                    f"Linha {line_number}: provider e provider_movie_id "
                    "devem ser preenchidos juntos."
                )

            if provider is not None:
                external_id = (provider, provider_movie_id)

                if external_id in seen_external_ids:
                    raise ValueError(
                        f"Linha {line_number}: identificador externo "
                        "duplicado no arquivo."
                    )

                seen_external_ids.add(external_id)

            runtime = movie["runtime_minutes"]

            if runtime is not None:
                if (
                    not runtime.isascii()
                    or not runtime.isdigit()
                    or int(runtime) <= 0
                    or int(runtime) > 9223372036854775807
                ):
                    raise ValueError(
                        f"Linha {line_number}: runtime_minutes deve ser "
                        "um inteiro positivo ou ficar vazio."
                    )

                movie["runtime_minutes"] = int(runtime)

            movies.append(movie)

    if not movies:
        raise ValueError(
            "O arquivo CSV não contém filmes."
        )

    return movies


def import_movies_csv(
    connection: sqlite3.Connection,
    csv_path: str | Path,
) -> int:
    """Insere ou atualiza filmes, usando movie_id como identidade.

    O arquivo é validado antes de qualquer alteração.

    A importação inteira ocorre em uma única transação.
    Se uma gravação falhar, nenhuma alteração do lote é mantida.

    Campos vazios representam informação desconhecida e substituem
    valores anteriores por NULL. O CSV deve conter registros completos,
    não atualizações parciais.
    """
    if connection.in_transaction:
        raise RuntimeError(
            "Finalize a transação atual antes de importar filmes."
        )

    movies = read_movies_csv(csv_path)

    statement = """
        INSERT INTO movies (
            movie_id,
            provider,
            provider_movie_id,
            title,
            synopsis,
            runtime_minutes,
            age_rating,
            source_url,
            source_updated_at
        )
        VALUES (
            :movie_id,
            :provider,
            :provider_movie_id,
            :title,
            :synopsis,
            :runtime_minutes,
            :age_rating,
            :source_url,
            :source_updated_at
        )
        ON CONFLICT (movie_id) DO UPDATE SET
            provider = excluded.provider,
            provider_movie_id = excluded.provider_movie_id,
            title = excluded.title,
            synopsis = excluded.synopsis,
            runtime_minutes = excluded.runtime_minutes,
            age_rating = excluded.age_rating,
            source_url = excluded.source_url,
            source_updated_at = excluded.source_updated_at
    """

    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.executemany(statement, movies)
        connection.commit()

    except Exception:
        connection.rollback()
        raise

    return len(movies)
