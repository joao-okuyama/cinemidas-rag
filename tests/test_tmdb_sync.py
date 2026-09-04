"""Testes da sincronização TMDB sem chamadas externas."""

import sqlite3
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, call

from src.booking.database import (
    connect_database,
    initialize_database,
)
from src.booking.normalized_movie_repository import (
    save_normalized_movies,
)
from src.booking.tmdb_client import TMDBClient, TMDBError
from src.booking.tmdb_normalizer import normalize_tmdb_movie
from src.booking.tmdb_sync import (
    sync_now_playing,
    TMDBSyncError,
)


class TMDBSyncTests(unittest.TestCase):
    def setUp(self):
        self.connection = connect_database(":memory:")
        self.addCleanup(self.connection.close)
        initialize_database(self.connection)

        self.collected_at = datetime(
            2026, 9, 4, 12, 30,
            tzinfo=timezone.utc,
        )

        # Registro anterior à sincronização.
        existing_movie = normalize_tmdb_movie(
            self.details(999),
            collected_at=self.collected_at,
        )
        save_normalized_movies(
            self.connection,
            [existing_movie],
        )

        self.client = Mock(spec=TMDBClient)
        self.client.get_movie_details.side_effect = self.details

        self.set_pages(
            self.page(1, 2, [101]),
            self.page(2, 2, [102]),
        )

    def details(self, movie_id):
        return {
            "id": movie_id,
            "title": f"Filme fictício {movie_id}",
            "overview": "Sinopse fictícia.",
            "runtime": 120,
            "poster_path": f"/{movie_id}.jpg",
            "genres": [
                {"id": 28, "name": "Ação"},
            ],
            "release_dates": {
                "results": [
                    {
                        "iso_3166_1": "BR",
                        "release_dates": [
                            {"type": 3, "certification": "12"}
                        ],
                    }
                ]
            },
        }

    def page(self, number, total_pages, movie_ids):
        return {
            "page": number,
            "total_pages": total_pages,
            "results": [
                {
                    "id": movie_id,
                    "title": f"Filme fictício {movie_id}",
                }
                for movie_id in movie_ids
            ],
        }

    def set_pages(self, *responses):
        self.client.get_now_playing_page.side_effect = list(
            responses
        )

    def run_sync(self, **overrides):
        arguments = {
            "collected_at": self.collected_at,
        }
        arguments.update(overrides)

        return sync_now_playing(
            self.connection,
            self.client,
            **arguments,
        )

    def snapshot(self):
        return {
            "movies": [
                tuple(row)
                for row in self.connection.execute(
                    "SELECT * FROM movies ORDER BY movie_id"
                )
            ],
            "genres": [
                tuple(row)
                for row in self.connection.execute(
                    "SELECT * FROM genres ORDER BY genre_id"
                )
            ],
            "movie_genres": [
                tuple(row)
                for row in self.connection.execute(
                    """
                    SELECT * FROM movie_genres
                    ORDER BY movie_id, genre_id
                    """
                )
            ],
        }

    def assert_database_unchanged(self, before):
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.connection.in_transaction)

    def test_multiple_pages_are_collected_and_saved(self):
        result = self.run_sync()

        self.assertEqual(result.pages_fetched, 2)
        self.assertEqual(result.movies_processed, 2)
        self.assertEqual(result.duplicate_ids, 0)
        self.assertEqual(result.warnings, {})
        self.assertEqual(
            result.collected_at,
            "2026-09-04T12:30:00+00:00",
        )

        self.assertEqual(
            self.client.get_now_playing_page.call_args_list,
            [call(page=1), call(page=2)],
        )
        self.assertEqual(
            self.client.get_movie_details.call_args_list,
            [call(101), call(102)],
        )

        for movie_id in ("TMDB-101", "TMDB-102"):
            movie = self.connection.execute(
                """
                SELECT poster_path, source_updated_at
                FROM movies
                WHERE movie_id = ?
                """,
                (movie_id,),
            ).fetchone()

            self.assertIsNotNone(movie)
            self.assertIsNotNone(movie["poster_path"])
            self.assertEqual(
                movie["source_updated_at"],
                result.collected_at,
            )

            genre_ids = [
                row[0]
                for row in self.connection.execute(
                    """
                    SELECT genre_id
                    FROM movie_genres
                    WHERE movie_id = ?
                    """,
                    (movie_id,),
                )
            ]

            self.assertEqual(genre_ids, [28])

        self.assertFalse(self.connection.in_transaction)

    def test_duplicate_ids_are_fetched_only_once(self):
        self.set_pages(
            self.page(1, 2, [101, 101]),
            self.page(2, 2, [101, 102]),
        )

        result = self.run_sync()

        self.assertEqual(result.movies_processed, 2)
        self.assertEqual(result.duplicate_ids, 2)
        self.assertEqual(
            self.client.get_movie_details.call_args_list,
            [call(101), call(102)],
        )

    def test_normalization_warnings_are_returned(self):
        self.set_pages(self.page(1, 1, [101]))

        payload = self.details(101)
        payload["runtime"] = None

        self.client.get_movie_details.side_effect = None
        self.client.get_movie_details.return_value = payload

        result = self.run_sync()

        self.assertIn("TMDB-101", result.warnings)
        self.assertTrue(
            any(
                "Duração" in warning
                for warning in result.warnings["TMDB-101"]
            )
        )

        runtime = self.connection.execute(
            """
            SELECT runtime_minutes
            FROM movies
            WHERE movie_id = 'TMDB-101'
            """
        ).fetchone()[0]

        self.assertIsNone(runtime)

    def test_empty_catalog_preserves_database(self):
        before = self.snapshot()
        self.set_pages(self.page(1, 0, []))

        with self.assertRaisesRegex(TMDBSyncError, "vazio"):
            self.run_sync()

        self.client.get_movie_details.assert_not_called()
        self.assert_database_unchanged(before)

    def test_empty_page_preserves_database(self):
        before = self.snapshot()
        self.set_pages(
            self.page(1, 2, [101]),
            self.page(2, 2, []),
        )

        with self.assertRaisesRegex(TMDBSyncError, "vazia"):
            self.run_sync()

        self.client.get_movie_details.assert_not_called()
        self.assert_database_unchanged(before)

    def test_changed_page_count_preserves_database(self):
        before = self.snapshot()
        self.set_pages(
            self.page(1, 2, [101]),
            self.page(2, 3, [102]),
        )

        with self.assertRaisesRegex(TMDBSyncError, "mudou"):
            self.run_sync()

        self.client.get_movie_details.assert_not_called()
        self.assert_database_unchanged(before)

    def test_page_limit_aborts_without_partial_import(self):
        before = self.snapshot()

        with self.assertRaisesRegex(TMDBSyncError, "limite"):
            self.run_sync(max_pages=1)

        self.client.get_now_playing_page.assert_called_once_with(
            page=1
        )
        self.client.get_movie_details.assert_not_called()
        self.assert_database_unchanged(before)

    def test_movie_limit_aborts_without_partial_import(self):
        before = self.snapshot()

        with self.assertRaisesRegex(TMDBSyncError, "limite"):
            self.run_sync(max_movies=1)

        self.client.get_movie_details.assert_not_called()
        self.assert_database_unchanged(before)

    def test_page_request_failure_preserves_database(self):
        before = self.snapshot()
        self.set_pages(
            self.page(1, 2, [101]),
            TMDBError("Falha simulada na segunda página."),
        )

        with self.assertRaises(TMDBError):
            self.run_sync()

        self.client.get_movie_details.assert_not_called()
        self.assert_database_unchanged(before)

    def test_detail_request_failure_preserves_database(self):
        before = self.snapshot()
        self.client.get_movie_details.side_effect = [
            self.details(101),
            TMDBError("Falha simulada nos detalhes."),
        ]

        with self.assertRaises(TMDBError):
            self.run_sync()

        self.assertEqual(
            self.client.get_movie_details.call_count,
            2,
        )
        self.assert_database_unchanged(before)

    def test_normalization_failure_preserves_database(self):
        before = self.snapshot()

        invalid_details = self.details(102)
        invalid_details["title"] = ""

        self.client.get_movie_details.side_effect = [
            self.details(101),
            invalid_details,
        ]

        with self.assertRaises(ValueError):
            self.run_sync()

        self.assert_database_unchanged(before)

    def test_database_failure_rolls_back_complete_import(self):
        before = self.snapshot()

        self.connection.execute(
            """
            CREATE TRIGGER fail_sync_test
            BEFORE INSERT ON movie_genres
            WHEN NEW.movie_id = 'TMDB-102'
            BEGIN
                SELECT RAISE(ABORT, 'Simulated sync failure');
            END;
            """
        )
        self.connection.commit()

        with self.assertRaisesRegex(
            sqlite3.IntegrityError,
            "Simulated sync failure",
        ):
            self.run_sync()

        self.assert_database_unchanged(before)

    def test_invalid_limits_are_rejected_before_requests(self):
        invalid_limits = [
            {"max_pages": 0},
            {"max_pages": -1},
            {"max_pages": True},
            {"max_pages": "2"},
            {"max_movies": 0},
            {"max_movies": -1},
            {"max_movies": True},
            {"max_movies": 1.5},
        ]

        before = self.snapshot()

        for arguments in invalid_limits:
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    self.run_sync(**arguments)

                self.assert_database_unchanged(before)

        self.client.get_now_playing_page.assert_not_called()
        self.client.get_movie_details.assert_not_called()

    def test_invalid_collection_time_is_rejected_before_requests(self):
        invalid_times = (
            datetime(2026, 9, 4, 12, 30),
            "2026-09-04T12:30:00Z",
            123,
        )

        for collected_at in invalid_times:
            with self.subTest(collected_at=collected_at):
                with self.assertRaises(ValueError):
                    self.run_sync(collected_at=collected_at)

        self.client.get_now_playing_page.assert_not_called()
        self.client.get_movie_details.assert_not_called()

    def test_active_transaction_is_rejected_and_preserved(self):
        self.connection.execute("BEGIN")

        with self.assertRaisesRegex(
            RuntimeError,
            "transação atual",
        ):
            self.run_sync()

        self.assertTrue(self.connection.in_transaction)
        self.client.get_now_playing_page.assert_not_called()

        self.connection.rollback()

    def test_disabled_foreign_keys_are_rejected(self):
        self.connection.execute("PRAGMA foreign_keys = OFF")

        with self.assertRaisesRegex(
            RuntimeError,
            "integridade referencial",
        ):
            self.run_sync()

        self.client.get_now_playing_page.assert_not_called()
        self.client.get_movie_details.assert_not_called()

    def test_movies_absent_from_collection_are_preserved(self):
        before_movie = tuple(
            self.connection.execute(
                "SELECT * FROM movies WHERE movie_id = 'TMDB-999'"
            ).fetchone()
        )

        self.run_sync()

        after_movie = tuple(
            self.connection.execute(
                "SELECT * FROM movies WHERE movie_id = 'TMDB-999'"
            ).fetchone()
        )

        self.assertEqual(after_movie, before_movie)

        genre_ids = [
            row[0]
            for row in self.connection.execute(
                """
                SELECT genre_id
                FROM movie_genres
                WHERE movie_id = 'TMDB-999'
                """
            )
        ]

        self.assertEqual(genre_ids, [28])


if __name__ == "__main__":
    unittest.main(verbosity=2)
