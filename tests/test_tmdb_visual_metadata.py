"""Testes da normalização de pôsteres e gêneros do TMDB."""

import copy
import unittest
from datetime import datetime, timezone

from src.booking.tmdb_normalizer import normalize_tmdb_movie


class TMDBVisualMetadataTests(unittest.TestCase):
    def setUp(self):
        self.collected_at = datetime(
            2026, 9, 4, 12, 30,
            tzinfo=timezone.utc,
        )

    def payload(self, **overrides):
        payload = {
            "id": 101,
            "title": "Filme fictício",
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
        return payload

    def normalize(self, payload):
        return normalize_tmdb_movie(
            payload,
            collected_at=self.collected_at,
        )

    def test_valid_poster_path_is_preserved(self):
        result = self.normalize(
            self.payload(poster_path="/poster_123-test.jpg")
        )

        self.assertTrue(result.poster_provided)
        self.assertEqual(
            result.poster_path,
            "/poster_123-test.jpg",
        )

        # O contrato básico continua separado dos campos visuais.
        self.assertNotIn("poster_path", result.record)

    def test_missing_poster_is_marked_as_not_provided(self):
        result = self.normalize(self.payload())

        self.assertFalse(result.poster_provided)
        self.assertIsNone(result.poster_path)

    def test_explicit_null_poster_is_marked_as_provided(self):
        result = self.normalize(
            self.payload(poster_path=None)
        )

        self.assertTrue(result.poster_provided)
        self.assertIsNone(result.poster_path)

    def test_invalid_poster_paths_are_rejected(self):
        invalid_paths = (
            "",
            "poster.jpg",
            "https://example.com/poster.jpg",
            "//example.com/poster.jpg",
            "/folder/poster.jpg",
            "/../poster.jpg",
            "/poster..jpg",
            "/poster.jpg?size=large",
            "/poster.jpg#fragment",
            "/poster\\image.jpg",
            "/poster%20image.jpg",
            "/.",
            "/",
            " /poster.jpg",
            "/poster.jpg ",
            "/poster.jpg\n",
        )

        for path in invalid_paths:
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    self.normalize(
                        self.payload(poster_path=path)
                    )

    def test_invalid_poster_types_are_rejected(self):
        for value in (123, True, [], {}):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.normalize(
                        self.payload(poster_path=value)
                    )

    def test_valid_genres_are_trimmed_and_sorted_by_id(self):
        result = self.normalize(
            self.payload(
                genres=[
                    {"id": 878, "name": " Ficção científica "},
                    {"id": 28, "name": " Ação "},
                    {"id": 12, "name": "Aventura"},
                ]
            )
        )

        self.assertEqual(
            result.genres,
            (
                (12, "Aventura"),
                (28, "Ação"),
                (878, "Ficção científica"),
            ),
        )
        self.assertNotIn("genres", result.record)

    def test_missing_or_null_genres_remain_unknown(self):
        payloads = [
            self.payload(),
            self.payload(genres=None),
        ]

        for payload in payloads:
            with self.subTest(payload=payload):
                result = self.normalize(payload)
                self.assertIsNone(result.genres)

    def test_explicit_empty_genres_produce_empty_tuple(self):
        result = self.normalize(
            self.payload(genres=[])
        )

        self.assertEqual(result.genres, ())
        self.assertIsNotNone(result.genres)

    def test_identical_genre_duplicates_are_removed(self):
        result = self.normalize(
            self.payload(
                genres=[
                    {"id": 28, "name": "Ação"},
                    {"id": 28, "name": " Ação "},
                ]
            )
        )

        self.assertEqual(result.genres, ((28, "Ação"),))

    def test_conflicting_names_for_same_genre_are_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "nomes divergentes",
        ):
            self.normalize(
                self.payload(
                    genres=[
                        {"id": 28, "name": "Ação"},
                        {"id": 28, "name": "Comédia"},
                    ]
                )
            )

    def test_invalid_genre_ids_are_rejected(self):
        invalid_ids = (
            None,
            0,
            -1,
            "28",
            28.5,
            True,
            9223372036854775808,
        )

        for genre_id in invalid_ids:
            with self.subTest(genre_id=genre_id):
                with self.assertRaises(ValueError):
                    self.normalize(
                        self.payload(
                            genres=[
                                {
                                    "id": genre_id,
                                    "name": "Ação",
                                }
                            ]
                        )
                    )

    def test_missing_or_invalid_genre_names_are_rejected(self):
        invalid_names = (
            None,
            "",
            "   ",
            123,
            True,
            [],
        )

        for name in invalid_names:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    self.normalize(
                        self.payload(
                            genres=[
                                {"id": 28, "name": name}
                            ]
                        )
                    )

        with self.assertRaises(ValueError):
            self.normalize(
                self.payload(genres=[{"id": 28}])
            )

    def test_malformed_genre_structures_are_rejected(self):
        invalid_values = (
            "Ação",
            {},
            123,
            [None],
            ["Ação"],
            [28],
            [{}],
        )

        for genres in invalid_values:
            with self.subTest(genres=genres):
                with self.assertRaises(ValueError):
                    self.normalize(
                        self.payload(genres=genres)
                    )

    def test_visual_metadata_does_not_mutate_original_payload(self):
        payload = self.payload(
            poster_path="/poster.jpg",
            genres=[
                {"id": 878, "name": " Ficção científica "},
                {"id": 28, "name": "Ação"},
                {"id": 28, "name": "Ação"},
            ],
        )
        original = copy.deepcopy(payload)

        result = self.normalize(payload)

        self.assertEqual(payload, original)
        self.assertEqual(
            result.genres,
            (
                (28, "Ação"),
                (878, "Ficção científica"),
            ),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
