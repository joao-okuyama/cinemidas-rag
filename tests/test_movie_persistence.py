"""Testes diretos da persistência e integração com o normalizador."""

import copy
import sqlite3
import unittest
from datetime import datetime, timezone

from src.booking.database import (
    connect_database,
    initialize_database,
)
from src.booking.movie_catalog import save_movies
from src.booking.tmdb_normalizer import normalize_tmdb_movie


class MoviePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.connection = connect_database(":memory:")
        self.addCleanup(self.connection.close)
        initialize_database(self.connection)

        self.collected_at = datetime(
            2026, 9, 4, 12, 30,
            tzinfo=timezone.utc,
        )

    def normalized_movie(self, movie_id=101, **overrides):
        payload = {
            "id": movie_id,
            "title": f"Filme fictício {movie_id}",
            "overview": "Sinopse fictícia.",
            "runtime": 120,
            "release_dates": {
                "results": [
                    {
                        "iso_3166_1": "BR",
                        "release_dates": [
                            {
                                "type": 3,
                                "certification": "12",
                            }
                        ],
                    }
                ]
            },
        }
        payload.update(overrides)

        return normalize_tmdb_movie(
            payload,
            collected_at=self.collected_at,
        )

    def record(self, tmdb_id=101, **overrides):
        record = self.normalized_movie(tmdb_id).record
        record.update(overrides)
        return record

    def snapshot(self):
        return [
            dict(row)
            for row in self.connection.execute(
                """
                SELECT
                    movie_id,
                    provider,
                    provider_movie_id,
                    title,
                    synopsis,
                    runtime_minutes,
                    age_rating,
                    source_url,
                    source_updated_at
                FROM movies
                ORDER BY movie_id
                """
            )
        ]

    def test_normalized_movie_is_saved_without_csv(self):
        normalized = self.normalized_movie()

        processed = save_movies(
            self.connection,
            [normalized.record],
        )

        self.assertEqual(processed, 1)
        self.assertEqual(
            self.snapshot(),
            [normalized.record],
        )
        self.assertFalse(self.connection.in_transaction)

    def test_repeated_save_updates_without_duplicates(self):
        original = self.record()

        save_movies(self.connection, [original])
        save_movies(self.connection, [original])

        self.assertEqual(self.snapshot(), [original])

        updated = self.record(
            title="Título atualizado",
            runtime_minutes=130,
        )

        processed = save_movies(
            self.connection,
            [updated],
        )

        self.assertEqual(processed, 1)
        self.assertEqual(self.snapshot(), [updated])

    def test_unknown_metadata_is_saved_as_null(self):
        normalized = self.normalized_movie(
            overview=None,
            runtime=None,
            release_dates={"results": []},
        )

        save_movies(
            self.connection,
            [normalized.record],
        )

        saved = self.snapshot()[0]

        self.assertIsNone(saved["synopsis"])
        self.assertIsNone(saved["runtime_minutes"])
        self.assertIsNone(saved["age_rating"])
        self.assertTrue(normalized.warnings)

        # Avisos não são colunas da tabela de filmes.
        self.assertNotIn("warnings", saved)

    def test_empty_or_invalid_batch_is_rejected(self):
        for records in (None, {}, (), [], "filmes"):
            with self.subTest(records=records):
                with self.assertRaises(ValueError):
                    save_movies(self.connection, records)

                self.assertEqual(self.snapshot(), [])
                self.assertFalse(self.connection.in_transaction)

    def test_missing_extra_or_non_dictionary_records_are_rejected(self):
        missing_field = self.record()
        del missing_field["source_url"]

        extra_field = self.record()
        extra_field["unexpected"] = "valor"

        for invalid_record in (
            missing_field,
            extra_field,
            None,
            "filme",
        ):
            with self.subTest(record=invalid_record):
                with self.assertRaises(ValueError):
                    save_movies(
                        self.connection,
                        [
                            self.record(102),
                            invalid_record,
                        ],
                    )

                # O primeiro registro válido também não foi gravado.
                self.assertEqual(self.snapshot(), [])

    def test_invalid_text_and_required_fields_are_rejected(self):
        invalid_fields = [
            {"movie_id": 101},
            {"movie_id": "   "},
            {"title": None},
            {"title": False},
            {"title": ""},
            {"synopsis": []},
            {"provider": 123},
            {"provider_movie_id": 101},
            {"age_rating": 12},
            {"source_url": {}},
            {"source_updated_at": 123},
        ]

        for fields in invalid_fields:
            with self.subTest(fields=fields):
                with self.assertRaises(ValueError):
                    save_movies(
                        self.connection,
                        [self.record(**fields)],
                    )

                self.assertEqual(self.snapshot(), [])

    def test_invalid_runtime_is_rejected_before_writing(self):
        invalid_values = (
            "120",
            True,
            0,
            -1,
            120.5,
            9223372036854775808,
        )

        for runtime in invalid_values:
            with self.subTest(runtime=runtime):
                with self.assertRaises(ValueError):
                    save_movies(
                        self.connection,
                        [
                            self.record(102),
                            self.record(
                                runtime_minutes=runtime,
                            ),
                        ],
                    )

                self.assertEqual(self.snapshot(), [])
                self.assertFalse(self.connection.in_transaction)

    def test_duplicate_identifiers_in_batch_are_rejected(self):
        duplicate_movie_id = self.record(
            provider_movie_id="999",
        )

        duplicate_external_id = self.record(
            102,
            provider_movie_id="101",
        )

        for conflicting_record in (
            duplicate_movie_id,
            duplicate_external_id,
        ):
            with self.subTest(record=conflicting_record):
                with self.assertRaises(ValueError):
                    save_movies(
                        self.connection,
                        [
                            self.record(),
                            conflicting_record,
                        ],
                    )

                self.assertEqual(self.snapshot(), [])

    def test_provider_fields_must_be_filled_together(self):
        invalid_pairs = [
            {
                "provider": None,
                "provider_movie_id": "101",
            },
            {
                "provider": "tmdb",
                "provider_movie_id": None,
            },
        ]

        for fields in invalid_pairs:
            with self.subTest(fields=fields):
                with self.assertRaises(ValueError):
                    save_movies(
                        self.connection,
                        [self.record(**fields)],
                    )

                self.assertEqual(self.snapshot(), [])

    def test_conflict_rolls_back_updates_and_inserts(self):
        save_movies(
            self.connection,
            [
                self.record(101),
                self.record(102),
            ],
        )
        before = self.snapshot()

        update_existing = self.record(
            101,
            title="Esta alteração deve ser desfeita",
        )
        insert_new = self.record(103)

        # O ID externo 102 pertence a um filme já salvo.
        conflicting_record = self.record(
            104,
            provider_movie_id="102",
        )

        with self.assertRaises(sqlite3.IntegrityError):
            save_movies(
                self.connection,
                [
                    update_existing,
                    insert_new,
                    conflicting_record,
                ],
            )

        # Desfaz tanto a atualização quanto a inserção anteriores.
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.connection.in_transaction)

    def test_active_transaction_is_rejected_and_preserved(self):
        self.connection.execute("BEGIN")

        with self.assertRaisesRegex(
            RuntimeError,
            "transação atual",
        ):
            save_movies(
                self.connection,
                [self.record()],
            )

        self.assertTrue(self.connection.in_transaction)
        self.assertEqual(self.snapshot(), [])

        self.connection.rollback()

    def test_input_records_are_not_modified(self):
        records = [
            self.record(
                title="  Título com espaços  ",
                synopsis="   ",
            )
        ]
        original = copy.deepcopy(records)

        save_movies(self.connection, records)

        self.assertEqual(records, original)

        saved = self.snapshot()[0]
        self.assertEqual(saved["title"], "Título com espaços")
        self.assertIsNone(saved["synopsis"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
