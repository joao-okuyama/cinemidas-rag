"""Testes da persistência conjunta de filmes, pôsteres e gêneros."""

import copy
import sqlite3
import unittest
from dataclasses import replace
from datetime import datetime, timezone

from src.booking.database import (
    connect_database,
    initialize_database,
)
from src.booking.movie_catalog import save_movies
from src.booking.normalized_movie_repository import (
    save_normalized_movies,
)
from src.booking.tmdb_normalizer import normalize_tmdb_movie


class NormalizedMovieRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.connection = connect_database(":memory:")
        self.addCleanup(self.connection.close)
        initialize_database(self.connection)

        self.collected_at = datetime(
            2026, 9, 4, 12, 30,
            tzinfo=timezone.utc,
        )

    def make_movie(self, tmdb_id=101, **overrides):
        payload = {
            "id": tmdb_id,
            "title": f"Filme fictício {tmdb_id}",
            "overview": "Sinopse fictícia.",
            "runtime": 120,
            "poster_path": "/original.jpg",
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
        payload.update(overrides)

        return normalize_tmdb_movie(
            payload,
            collected_at=self.collected_at,
        )

    def get_movie(self, movie_id="TMDB-101"):
        row = self.connection.execute(
            "SELECT * FROM movies WHERE movie_id = ?",
            (movie_id,),
        ).fetchone()

        return dict(row) if row is not None else None

    def genres_for(self, movie_id="TMDB-101"):
        return [
            tuple(row)
            for row in self.connection.execute(
                """
                SELECT g.genre_id, g.name
                FROM genres AS g
                JOIN movie_genres AS mg
                    ON mg.genre_id = g.genre_id
                WHERE mg.movie_id = ?
                ORDER BY g.genre_id
                """,
                (movie_id,),
            )
        ]

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

    def test_movie_poster_and_genres_are_saved(self):
        processed = save_normalized_movies(
            self.connection,
            [self.make_movie()],
        )

        saved = self.get_movie()

        self.assertEqual(processed, 1)
        self.assertEqual(saved["title"], "Filme fictício 101")
        self.assertEqual(saved["poster_path"], "/original.jpg")
        self.assertEqual(self.genres_for(), [(28, "Ação")])
        self.assertFalse(self.connection.in_transaction)

    def test_repeated_save_does_not_duplicate_data(self):
        movie = self.make_movie()

        save_normalized_movies(self.connection, [movie])
        before = self.snapshot()

        save_normalized_movies(self.connection, [movie])

        self.assertEqual(self.snapshot(), before)

    def test_update_replaces_poster_and_genre_associations(self):
        save_normalized_movies(
            self.connection,
            [self.make_movie()],
        )

        updated = self.make_movie(
            title="Título atualizado",
            poster_path="/updated.jpg",
            genres=[{"id": 12, "name": "Aventura"}],
        )

        save_normalized_movies(self.connection, [updated])

        saved = self.get_movie()

        self.assertEqual(saved["title"], "Título atualizado")
        self.assertEqual(saved["poster_path"], "/updated.jpg")
        self.assertEqual(self.genres_for(), [(12, "Aventura")])

        # O gênero antigo permanece no catálogo global.
        old_genre = self.connection.execute(
            "SELECT name FROM genres WHERE genre_id = 28"
        ).fetchone()

        self.assertIsNotNone(old_genre)
        self.assertEqual(old_genre["name"], "Ação")

    def test_unknown_visual_fields_preserve_existing_values(self):
        save_normalized_movies(
            self.connection,
            [self.make_movie()],
        )

        updated = replace(
            self.make_movie(title="Título atualizado"),
            poster_provided=False,
            poster_path=None,
            genres=None,
        )

        save_normalized_movies(self.connection, [updated])

        saved = self.get_movie()

        self.assertEqual(saved["title"], "Título atualizado")
        self.assertEqual(saved["poster_path"], "/original.jpg")
        self.assertEqual(self.genres_for(), [(28, "Ação")])

    def test_explicit_removal_only_affects_selected_movie(self):
        save_normalized_movies(
            self.connection,
            [
                self.make_movie(101),
                self.make_movie(102),
            ],
        )

        updated = self.make_movie(
            poster_path=None,
            genres=[],
        )

        save_normalized_movies(self.connection, [updated])

        self.assertIsNone(self.get_movie()["poster_path"])
        self.assertEqual(self.genres_for(), [])

        self.assertEqual(
            self.get_movie("TMDB-102")["poster_path"],
            "/original.jpg",
        )
        self.assertEqual(
            self.genres_for("TMDB-102"),
            [(28, "Ação")],
        )

    def test_basic_save_preserves_visual_metadata(self):
        save_normalized_movies(
            self.connection,
            [self.make_movie()],
        )

        basic_record = dict(
            self.make_movie(title="Atualização básica").record
        )

        save_movies(self.connection, [basic_record])

        saved = self.get_movie()

        self.assertEqual(saved["title"], "Atualização básica")
        self.assertEqual(saved["poster_path"], "/original.jpg")
        self.assertEqual(self.genres_for(), [(28, "Ação")])

    def test_genre_failure_rolls_back_entire_batch(self):
        save_normalized_movies(
            self.connection,
            [self.make_movie()],
        )
        before = self.snapshot()

        # Falha controlada exclusivamente neste banco de teste.
        self.connection.execute(
            """
            CREATE TRIGGER fail_test_genre
            BEFORE INSERT ON movie_genres
            WHEN NEW.genre_id = 12
            BEGIN
                SELECT RAISE(ABORT, 'Simulated genre failure');
            END;
            """
        )

        updated = self.make_movie(
            title="Não deve permanecer",
            poster_path="/must-not-remain.jpg",
            genres=[{"id": 12, "name": "Aventura"}],
        )
        new_movie = self.make_movie(103)

        with self.assertRaisesRegex(
            sqlite3.IntegrityError,
            "Simulated genre failure",
        ):
            save_normalized_movies(
                self.connection,
                [updated, new_movie],
            )

        # Verifica os filmes, os pôsteres, os gêneros globais
        # e todas as associações anteriores.
        self.assertEqual(self.snapshot(), before)
        self.assertIsNone(self.get_movie("TMDB-103"))
        self.assertFalse(self.connection.in_transaction)

    def test_invalid_batches_and_items_are_rejected(self):
        invalid_batches = (
            None,
            [],
            (),
            {},
            [None],
            [{"movie_id": "TMDB-101"}],
        )

        before = self.snapshot()

        for batch in invalid_batches:
            with self.subTest(batch=batch):
                with self.assertRaises(ValueError):
                    save_normalized_movies(
                        self.connection,
                        batch,
                    )

                self.assertEqual(self.snapshot(), before)
                self.assertFalse(self.connection.in_transaction)

    def test_invalid_basic_records_are_rejected_before_writing(self):
        invalid_records = [
            {"title": ""},
            {"runtime_minutes": True},
            {"provider": "another-provider"},
        ]

        before = self.snapshot()

        for overrides in invalid_records:
            with self.subTest(overrides=overrides):
                invalid = self.make_movie(102)
                invalid.record.update(overrides)

                with self.assertRaises(ValueError):
                    save_normalized_movies(
                        self.connection,
                        [self.make_movie(), invalid],
                    )

                self.assertEqual(self.snapshot(), before)

    def test_modified_invalid_visual_metadata_is_rejected(self):
        invalid_fields = [
            {"poster_provided": "yes"},
            {
                "poster_provided": False,
                "poster_path": "/inconsistent.jpg",
            },
            {"poster_path": "https://example.com/poster.jpg"},
            {"genres": [(28, "Ação")]},
            {"genres": ((28,),)},
            {"genres": ((True, "Ação"),)},
            {"genres": ((28, ""),)},
        ]

        before = self.snapshot()

        for fields in invalid_fields:
            with self.subTest(fields=fields):
                invalid = replace(
                    self.make_movie(102),
                    **fields,
                )

                with self.assertRaises(ValueError):
                    save_normalized_movies(
                        self.connection,
                        [self.make_movie(), invalid],
                    )

                self.assertEqual(self.snapshot(), before)

    def test_conflicting_genre_names_across_movies_are_rejected(self):
        first = self.make_movie(101)
        second = self.make_movie(
            102,
            genres=[{"id": 28, "name": "Nome divergente"}],
        )
        before = self.snapshot()

        with self.assertRaisesRegex(
            ValueError,
            "nomes divergentes",
        ):
            save_normalized_movies(
                self.connection,
                [first, second],
            )

        self.assertEqual(self.snapshot(), before)

    def test_active_transaction_is_rejected_and_preserved(self):
        self.connection.execute("BEGIN")

        with self.assertRaisesRegex(
            RuntimeError,
            "transação atual",
        ):
            save_normalized_movies(
                self.connection,
                [self.make_movie()],
            )

        self.assertTrue(self.connection.in_transaction)
        self.assertIsNone(self.get_movie())

        self.connection.rollback()

    def test_disabled_foreign_keys_are_rejected(self):
        self.connection.execute("PRAGMA foreign_keys = OFF")

        with self.assertRaisesRegex(
            RuntimeError,
            "integridade referencial",
        ):
            save_normalized_movies(
                self.connection,
                [self.make_movie()],
            )

        self.assertIsNone(self.get_movie())

    def test_input_objects_are_not_modified(self):
        movies = [
            self.make_movie(101),
            self.make_movie(
                102,
                genres=[{"id": 12, "name": "Aventura"}],
            ),
        ]
        original = copy.deepcopy(movies)

        save_normalized_movies(self.connection, movies)

        self.assertEqual(movies, original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
