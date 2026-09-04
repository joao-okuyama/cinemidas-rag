import copy
import unittest
from datetime import datetime, timedelta, timezone

from src.booking.tmdb_normalizer import normalize_tmdb_movie


class TMDBNormalizerTests(unittest.TestCase):
    def setUp(self):
        self.collected_at = datetime(
            2026, 9, 4, 12, 30, 0,
            tzinfo=timezone.utc,
        )

    def payload(self, **overrides):
        data = {
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
        data.update(overrides)
        return data

    def normalize(self, payload):
        return normalize_tmdb_movie(
            payload,
            collected_at=self.collected_at,
        )

    def test_complete_movie_is_normalized(self):
        result = self.normalize(self.payload())

        self.assertEqual(
            result.record,
            {
                "movie_id": "TMDB-101",
                "provider": "tmdb",
                "provider_movie_id": "101",
                "title": "Filme fictício",
                "synopsis": "Sinopse fictícia.",
                "runtime_minutes": 120,
                "age_rating": "12",
                "source_url": (
                    "https://www.themoviedb.org/movie/101"
                ),
                "source_updated_at": (
                    "2026-09-04T12:30:00+00:00"
                ),
            },
        )
        self.assertEqual(result.warnings, ())

    def test_text_is_trimmed(self):
        payload = self.payload(
            title="  Filme fictício  ",
            overview="  Sinopse fictícia.  ",
        )
        payload["release_dates"]["results"][0][
            "release_dates"
        ][0]["certification"] = " 12 "

        result = self.normalize(payload)

        self.assertEqual(result.record["title"], "Filme fictício")
        self.assertEqual(
            result.record["synopsis"],
            "Sinopse fictícia.",
        )
        self.assertEqual(result.record["age_rating"], "12")

    def test_invalid_movie_ids_are_rejected(self):
        for movie_id in (None, 0, -1, "101", 1.5, True):
            with self.subTest(movie_id=movie_id):
                with self.assertRaises(ValueError):
                    self.normalize(self.payload(id=movie_id))

    def test_invalid_titles_are_rejected(self):
        for title in (None, "", "   ", 123, [], True):
            with self.subTest(title=title):
                with self.assertRaises(ValueError):
                    self.normalize(self.payload(title=title))

    def test_non_object_payload_is_rejected(self):
        for payload in (None, [], "filme", 123):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    self.normalize(payload)

    def test_missing_synopsis_becomes_null_with_warning(self):
        for overview in (None, "", "   "):
            with self.subTest(overview=overview):
                result = self.normalize(
                    self.payload(overview=overview)
                )

                self.assertIsNone(result.record["synopsis"])
                self.assertIn(
                    "Sinopse não informada.",
                    result.warnings,
                )

    def test_invalid_synopsis_type_is_rejected(self):
        for overview in (123, [], {}, True):
            with self.subTest(overview=overview):
                with self.assertRaises(ValueError):
                    self.normalize(
                        self.payload(overview=overview)
                    )

    def test_invalid_runtime_becomes_unknown_with_warning(self):
        invalid_values = (
            None,
            0,
            -1,
            "120",
            120.5,
            True,
            9223372036854775808,
        )

        for runtime in invalid_values:
            with self.subTest(runtime=runtime):
                result = self.normalize(
                    self.payload(runtime=runtime)
                )

                self.assertIsNone(
                    result.record["runtime_minutes"]
                )
                self.assertTrue(
                    any(
                        "Duração" in warning
                        for warning in result.warnings
                    )
                )

    def test_missing_release_data_becomes_unknown_with_warning(self):
        payload = self.payload()
        del payload["release_dates"]

        result = self.normalize(payload)

        self.assertIsNone(result.record["age_rating"])
        self.assertIn(
            "Dados de classificação não retornados pelo TMDB.",
            result.warnings,
        )

    def test_other_countries_and_non_theatrical_releases_are_ignored(self):
        payload = self.payload(
            release_dates={
                "results": [
                    {
                        "iso_3166_1": "US",
                        "release_dates": [
                            {"type": 3, "certification": "PG-13"}
                        ],
                    },
                    {
                        "iso_3166_1": "BR",
                        "release_dates": [
                            {"type": 4, "certification": "16"},
                            {"type": 6, "certification": "18"},
                            {"type": 3, "certification": ""},
                        ],
                    },
                ]
            }
        )

        result = self.normalize(payload)

        self.assertIsNone(result.record["age_rating"])
        self.assertIn(
            "Classificação cinematográfica brasileira não informada.",
            result.warnings,
        )

    def test_repeated_identical_certifications_are_not_a_conflict(self):
        payload = self.payload()
        payload["release_dates"]["results"][0][
            "release_dates"
        ] = [
            {"type": 2, "certification": "12"},
            {"type": 3, "certification": "12"},
        ]

        result = self.normalize(payload)

        self.assertEqual(result.record["age_rating"], "12")
        self.assertEqual(result.warnings, ())

    def test_conflicting_certifications_are_not_silently_selected(self):
        payload = self.payload()
        payload["release_dates"]["results"][0][
            "release_dates"
        ] = [
            {"type": 2, "certification": "12"},
            {"type": 3, "certification": "16"},
        ]

        result = self.normalize(payload)

        self.assertIsNone(result.record["age_rating"])
        self.assertIn(
            "Classificações brasileiras divergentes: "
            "12, 16. Nenhuma foi selecionada.",
            result.warnings,
        )

    def test_malformed_release_data_is_rejected(self):
        invalid_values = [
            [],
            {},
            {"results": None},
            {"results": [None]},
            {
                "results": [
                    {
                        "iso_3166_1": "BR",
                        "release_dates": None,
                    }
                ]
            },
            {
                "results": [
                    {
                        "iso_3166_1": "BR",
                        "release_dates": [None],
                    }
                ]
            },
            {
                "results": [
                    {
                        "iso_3166_1": "BR",
                        "release_dates": [
                            {"type": 3, "certification": 12}
                        ],
                    }
                ]
            },
        ]

        for release_data in invalid_values:
            with self.subTest(release_data=release_data):
                with self.assertRaises(ValueError):
                    self.normalize(
                        self.payload(release_dates=release_data)
                    )

    def test_collection_time_is_converted_to_utc(self):
        local_time = datetime(
            2026, 9, 4, 9, 30, 0,
            tzinfo=timezone(timedelta(hours=-3)),
        )

        result = normalize_tmdb_movie(
            self.payload(),
            collected_at=local_time,
        )

        self.assertEqual(
            result.record["source_updated_at"],
            "2026-09-04T12:30:00+00:00",
        )

    def test_missing_timezone_or_invalid_collection_time_is_rejected(self):
        invalid_values = (
            datetime(2026, 9, 4, 12, 30),
            None,
            "2026-09-04T12:30:00Z",
        )

        for collected_at in invalid_values:
            with self.subTest(collected_at=collected_at):
                with self.assertRaises(ValueError):
                    normalize_tmdb_movie(
                        self.payload(),
                        collected_at=collected_at,
                    )

    def test_original_payload_is_not_modified(self):
        payload = self.payload()
        original = copy.deepcopy(payload)

        self.normalize(payload)

        self.assertEqual(payload, original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
