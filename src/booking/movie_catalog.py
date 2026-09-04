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


def _prepare_movie_records(records: list[dict]) -> list[dict]:
    """Valida o lote e devolve cópias normalizadas.

    Não acessa o banco e não modifica os registros recebidos.
    """
    if not isinstance(records, list) or not records:
        raise ValueError(
            "Informe uma lista não vazia de filmes."
        )

    movies = []
    seen_movie_ids = set()
    seen_external_ids = set()
    expected_fields = set(CSV_COLUMNS)

    for position, record in enumerate(records, start=1):
        if (
            not isinstance(record, dict)
            or set(record) != expected_fields
        ):
            raise ValueError(
                f"Registro {position}: campos diferentes "
                "dos esperados para o catálogo."
            )

        movie = dict(record)

        for field in CSV_COLUMNS:
            if field == "runtime_minutes":
                continue

            value = movie[field]

            if value is not None and not isinstance(value, str):
                raise ValueError(
                    f"Registro {position}: {field} deve ser "
                    "texto ou nulo."
                )

            if value is None:
                movie[field] = None
            else:
                movie[field] = value.strip() or None

        movie_id = movie["movie_id"]

        if not movie_id or not movie["title"]:
            raise ValueError(
                f"Registro {position}: movie_id e title "
                "são obrigatórios."
            )

        if movie_id in seen_movie_ids:
            raise ValueError(
                f"Registro {position}: movie_id duplicado no lote."
            )

        seen_movie_ids.add(movie_id)

        provider = movie["provider"]
        provider_movie_id = movie["provider_movie_id"]

        if (provider is None) != (provider_movie_id is None):
            raise ValueError(
                f"Registro {position}: provider e provider_movie_id "
                "devem ser preenchidos juntos."
            )

        if provider is not None:
            external_id = (provider, provider_movie_id)

            if external_id in seen_external_ids:
                raise ValueError(
                    f"Registro {position}: identificador externo "
                    "duplicado no lote."
                )

            seen_external_ids.add(external_id)

        runtime = movie["runtime_minutes"]

        if runtime is not None and (
            type(runtime) is not int
            or runtime <= 0
            or runtime > 9223372036854775807
        ):
            raise ValueError(
                f"Registro {position}: runtime_minutes deve ser "
                "um inteiro positivo ou nulo."
            )

        movies.append(movie)

    return movies


def _write_movie_records(
    connection: sqlite3.Connection,
    movies: list[dict],
) -> None:
    """Grava registros previamente validados.

    Exige uma transação aberta pelo chamador.
    Não confirma nem desfaz a transação.
    """
    if not connection.in_transaction:
        raise RuntimeError(
            "A gravação interna exige uma transação ativa."
        )

    connection.executemany(
        """
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
        """,
        movies,
    )


def save_movies(
    connection: sqlite3.Connection,
    records: list[dict],
) -> int:
    """Valida e grava os campos básicos em uma única transação.

    Atualiza filmes pelo movie_id e não exclui filmes ausentes.
    Campos básicos opcionais vazios substituem valores por NULL.

    Não altera pôsteres nem associações de gênero.

    Retorna a quantidade de registros processados, não apenas inseridos.
    """
    if connection.in_transaction:
        raise RuntimeError(
            "Finalize a transação atual antes de salvar filmes."
        )

    movies = _prepare_movie_records(records)

    try:
        connection.execute("BEGIN IMMEDIATE")
        _write_movie_records(connection, movies)
        connection.commit()

    except Exception:
        connection.rollback()
        raise

    return len(movies)


def import_movies_csv(
    connection: sqlite3.Connection,
    csv_path: str | Path,
) -> int:
    """Lê o CSV e delega a gravação à função compartilhada."""
    if connection.in_transaction:
        raise RuntimeError(
            "Finalize a transação atual antes de importar filmes."
        )

    records = read_movies_csv(csv_path)

    return save_movies(connection, records)
