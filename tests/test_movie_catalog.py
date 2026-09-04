import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.booking.database import (
    connect_database,
    initialize_database,
)
from src.booking.movie_catalog import (
    CSV_COLUMNS,
    import_movies_csv,
)


class MovieCatalogTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory(
            prefix="cinemidas-movie-tests-"
        )
        self.addCleanup(temporary_directory.cleanup)

        directory = Path(temporary_directory.name)
        self.csv_path = directory / "movies.csv"

        self.connection = connect_database(
            directory / "test.db"
        )
        self.addCleanup(self.connection.close)

        initialize_database(self.connection)

    def movie(self, **overrides):
        record = {
            "movie_id": "TEST-MOVIE-001",
            "provider": "test-provider",
            "provider_movie_id": "001",
            "title": "Filme fictício de teste",
            "synopsis": "Uma sinopse fictícia, com vírgula.",
            "runtime_minutes": "120",
            "age_rating": "",
            "source_url": "",
            "source_updated_at": "",
        }
        record.update(overrides)
        return record

    def write_csv(self, records):
        with self.csv_path.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=CSV_COLUMNS,
            )
            writer.writeheader()
            writer.writerows(records)

    def import_records(self, records):
        self.write_csv(records)

        return import_movies_csv(
            self.connection,
            self.csv_path,
        )

    def snapshot(self):
        return [
            tuple(row)
            for row in self.connection.execute(
                "SELECT * FROM movies ORDER BY movie_id"
            )
        ]

    def test_valid_movie_is_imported(self):
        count = self.import_records([self.movie()])

        row = self.connection.execute(
            "SELECT * FROM movies"
        ).fetchone()

        self.assertEqual(count, 1)
        self.assertEqual(
            row["title"],
            "Filme fictício de teste",
        )
        self.assertEqual(
            row["synopsis"],
            "Uma sinopse fictícia, com vírgula.",
        )
        self.assertEqual(row["runtime_minutes"], 120)
        self.assertIsNone(row["age_rating"])

    def test_repeated_import_does_not_duplicate_movies(self):
        records = [self.movie()]

        self.import_records(records)
        before = self.snapshot()

        self.import_records(records)

        self.assertEqual(self.snapshot(), before)

    def test_existing_movie_is_updated(self):
        self.import_records([self.movie()])

        self.import_records([
            self.movie(
                title="Título atualizado",
                runtime_minutes="130",
            )
        ])

        rows = self.connection.execute(
            "SELECT title, runtime_minutes FROM movies"
        ).fetchall()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Título atualizado")
        self.assertEqual(rows[0]["runtime_minutes"], 130)

    def test_blank_fields_replace_previous_values_with_null(self):
        self.import_records([
            self.movie(age_rating="CLASSIFICACAO-DE-TESTE")
        ])

        self.import_records([
            self.movie(
                synopsis="",
                runtime_minutes="",
                age_rating="",
            )
        ])

        row = self.connection.execute(
            """
            SELECT synopsis, runtime_minutes, age_rating
            FROM movies
            """
        ).fetchone()

        self.assertIsNone(row["synopsis"])
        self.assertIsNone(row["runtime_minutes"])
        self.assertIsNone(row["age_rating"])

    def test_movies_absent_from_csv_are_preserved(self):
        second_movie = self.movie(
            movie_id="TEST-MOVIE-002",
            provider_movie_id="002",
        )

        self.import_records([
            self.movie(),
            second_movie,
        ])

        self.import_records([
            self.movie(title="Título atualizado")
        ])

        movie_ids = {
            row["movie_id"]
            for row in self.connection.execute(
                "SELECT movie_id FROM movies"
            )
        }

        self.assertEqual(
            movie_ids,
            {"TEST-MOVIE-001", "TEST-MOVIE-002"},
        )

    def test_invalid_header_is_rejected(self):
        with self.csv_path.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(["movie_id", "title"])
            writer.writerow(["TEST-MOVIE-001", "Teste"])

        with self.assertRaisesRegex(ValueError, "Cabeçalho"):
            import_movies_csv(
                self.connection,
                self.csv_path,
            )

        self.assertEqual(self.snapshot(), [])

    def test_csv_without_movies_is_rejected(self):
        self.write_csv([])

        with self.assertRaisesRegex(
            ValueError,
            "não contém filmes",
        ):
            import_movies_csv(
                self.connection,
                self.csv_path,
            )

    def test_required_fields_are_validated_before_writing(self):
        for field in ("movie_id", "title"):
            with self.subTest(field=field):
                invalid_movie = self.movie(
                    movie_id="TEST-MOVIE-002",
                    provider_movie_id="002",
                )
                invalid_movie[field] = "   "

                with self.assertRaises(ValueError):
                    self.import_records([
                        self.movie(),
                        invalid_movie,
                    ])

                self.assertEqual(self.snapshot(), [])

    def test_duplicate_movie_ids_in_csv_are_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "movie_id duplicado",
        ):
            self.import_records([
                self.movie(),
                self.movie(provider_movie_id="002"),
            ])

        self.assertEqual(self.snapshot(), [])

    def test_provider_fields_must_be_filled_together(self):
        invalid_pairs = [
            {"provider": "", "provider_movie_id": "001"},
            {"provider": "test-provider", "provider_movie_id": ""},
        ]

        for fields in invalid_pairs:
            with self.subTest(fields=fields):
                with self.assertRaises(ValueError):
                    self.import_records([
                        self.movie(**fields)
                    ])

                self.assertEqual(self.snapshot(), [])

    def test_duplicate_external_ids_in_csv_are_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "identificador externo",
        ):
            self.import_records([
                self.movie(),
                self.movie(movie_id="TEST-MOVIE-002"),
            ])

        self.assertEqual(self.snapshot(), [])

    def test_invalid_runtime_is_rejected(self):
        invalid_values = (
            "0",
            "-1",
            "1.5",
            "abc",
            "１２０",
            "9223372036854775808",
        )

        for runtime in invalid_values:
            with self.subTest(runtime=runtime):
                with self.assertRaises(ValueError):
                    self.import_records([
                        self.movie(runtime_minutes=runtime)
                    ])

                self.assertEqual(self.snapshot(), [])

    def test_wrong_number_of_csv_fields_is_rejected(self):
        valid_record = self.movie()
        valid_values = [
            valid_record[column]
            for column in CSV_COLUMNS
        ]

        malformed_rows = [
            valid_values[:-1],
            valid_values + ["campo extra"],
        ]

        for malformed_row in malformed_rows:
            with self.subTest(field_count=len(malformed_row)):
                with self.csv_path.open(
                    "w",
                    encoding="utf-8",
                    newline="",
                ) as csv_file:
                    writer = csv.writer(csv_file)
                    writer.writerow(CSV_COLUMNS)
                    writer.writerow(malformed_row)

                with self.assertRaises(ValueError):
                    import_movies_csv(
                        self.connection,
                        self.csv_path,
                    )

                self.assertEqual(self.snapshot(), [])

    def test_database_conflict_rolls_back_entire_batch(self):
        self.import_records([self.movie()])
        before = self.snapshot()

        valid_new_movie = self.movie(
            movie_id="TEST-MOVIE-002",
            provider_movie_id="002",
        )

        # Conflita com o identificador externo já salvo no banco,
        # mas não com outro registro do arquivo deste lote.
        conflicting_movie = self.movie(
            movie_id="TEST-MOVIE-003",
            provider_movie_id="001",
        )

        with self.assertRaises(sqlite3.IntegrityError):
            self.import_records([
                valid_new_movie,
                conflicting_movie,
            ])

        # Nem mesmo o primeiro filme válido pode permanecer salvo.
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.connection.in_transaction)

    def test_active_transaction_is_rejected_and_preserved(self):
        self.write_csv([self.movie()])
        self.connection.execute("BEGIN")

        with self.assertRaisesRegex(
            RuntimeError,
            "transação atual",
        ):
            import_movies_csv(
                self.connection,
                self.csv_path,
            )

        self.assertTrue(self.connection.in_transaction)
        self.assertEqual(self.snapshot(), [])

        self.connection.rollback()


if __name__ == "__main__":
    unittest.main(verbosity=2)
