"""Testes das regras de publicação da vitrine CineViva."""

import copy
import unittest
from datetime import datetime, timedelta, timezone

from src.booking.catalog_policy import (
    evaluate_catalog_visibility,
    rank_catalog_movies,
)


class CatalogPolicyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(
            2026, 9, 4, 12, 30,
            tzinfo=timezone.utc,
        )
        self.collected_at = self.now - timedelta(hours=1)

    def movie(self, **overrides):
        movie = {
            "movie_id": "TMDB-101",
            "title": "Filme fictício",
            "runtime_minutes": 120,
            "poster_path": "/poster.jpg",
            "synopsis": "Sinopse fictícia.",
            "popularity": 25.0,
        }
        movie.update(overrides)
        return movie

    def evaluate(self, movie=None, **overrides):
        arguments = {
            "in_latest_collection": True,
            "has_br_theatrical_release": True,
            "has_future_sessions": True,
            "collection_finished_at": self.collected_at,
            "now": self.now,
        }
        arguments.update(overrides)

        return evaluate_catalog_visibility(
            self.movie() if movie is None else movie,
            **arguments,
        )

    def test_complete_movie_is_visible_with_session_options(self):
        movie = self.movie()
        original = copy.deepcopy(movie)

        result = self.evaluate(movie)

        self.assertTrue(result.show_in_catalog)
        self.assertTrue(result.show_session_options)
        self.assertEqual(result.reasons, ())
        self.assertEqual(movie, original)

    def test_movie_without_sessions_remains_visible_without_options(self):
        result = self.evaluate(has_future_sessions=False)

        self.assertTrue(result.show_in_catalog)
        self.assertFalse(result.show_session_options)
        self.assertEqual(result.reasons, ("no_future_sessions",))

    def test_movie_outside_latest_collection_is_hidden(self):
        result = self.evaluate(in_latest_collection=False)

        self.assertFalse(result.show_in_catalog)
        self.assertFalse(result.show_session_options)
        self.assertIn("not_in_latest_collection", result.reasons)

    def test_movie_without_brazilian_theatrical_release_is_hidden(self):
        result = self.evaluate(has_br_theatrical_release=False)

        self.assertFalse(result.show_in_catalog)
        self.assertFalse(result.show_session_options)
        self.assertIn("no_br_theatrical_release", result.reasons)

    def test_collection_older_than_limit_is_stale(self):
        result = self.evaluate(
            collection_finished_at=(
                self.now - timedelta(hours=48, seconds=1)
            )
        )

        self.assertFalse(result.show_in_catalog)
        self.assertFalse(result.show_session_options)
        self.assertIn("stale_collection", result.reasons)

    def test_collection_at_exact_age_limit_is_accepted(self):
        result = self.evaluate(
            collection_finished_at=(
                self.now - timedelta(hours=48)
            )
        )

        self.assertTrue(result.show_in_catalog)
        self.assertNotIn("stale_collection", result.reasons)

    def test_runtime_rules_include_exact_minimum(self):
        accepted = self.evaluate(
            self.movie(runtime_minutes=60)
        )
        self.assertTrue(accepted.show_in_catalog)

        rejected = self.evaluate(
            self.movie(runtime_minutes=59)
        )
        self.assertFalse(rejected.show_in_catalog)
        self.assertIn(
            "runtime_below_minimum",
            rejected.reasons,
        )

        for runtime in (None, 0, -1, True, "120", 120.5):
            with self.subTest(runtime=runtime):
                result = self.evaluate(
                    self.movie(runtime_minutes=runtime)
                )

                self.assertFalse(result.show_in_catalog)
                self.assertIn("unknown_runtime", result.reasons)

    def test_missing_display_fields_prevent_publication(self):
        expected_reasons = {
            "title": "missing_title",
            "poster_path": "missing_poster",
            "synopsis": "missing_synopsis",
        }

        for field, reason in expected_reasons.items():
            for value in (None, "", "   ", 123):
                with self.subTest(field=field, value=value):
                    result = self.evaluate(
                        self.movie(**{field: value})
                    )

                    self.assertFalse(result.show_in_catalog)
                    self.assertFalse(result.show_session_options)
                    self.assertIn(reason, result.reasons)

    def test_multiple_rejection_reasons_are_reported(self):
        result = self.evaluate(
            self.movie(
                runtime_minutes=20,
                poster_path=None,
            ),
            in_latest_collection=False,
            has_br_theatrical_release=False,
            has_future_sessions=False,
            collection_finished_at=(
                self.now - timedelta(hours=49)
            ),
        )

        self.assertEqual(
            set(result.reasons),
            {
                "not_in_latest_collection",
                "no_br_theatrical_release",
                "stale_collection",
                "runtime_below_minimum",
                "missing_poster",
                "no_future_sessions",
            },
        )

    def test_invalid_movie_and_indicator_types_are_rejected(self):
        for movie in ([], "filme", 123):
            with self.subTest(movie=movie):
                with self.assertRaises(ValueError):
                    self.evaluate(movie)

        for field in (
            "in_latest_collection",
            "has_br_theatrical_release",
            "has_future_sessions",
        ):
            for value in (None, 1, "true"):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        self.evaluate(**{field: value})

    def test_invalid_or_future_timestamps_are_rejected(self):
        invalid_values = (
            None,
            "2026-09-04",
            datetime(2026, 9, 4, 12, 30),
        )

        for field in ("collection_finished_at", "now"):
            for value in invalid_values:
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        self.evaluate(**{field: value})

        with self.assertRaises(ValueError):
            self.evaluate(
                collection_finished_at=(
                    self.now + timedelta(seconds=1)
                )
            )

    def test_policy_configuration_is_validated_and_configurable(self):
        for minimum in (0, -1, True, "60"):
            with self.subTest(minimum=minimum):
                with self.assertRaises(ValueError):
                    self.evaluate(minimum_runtime=minimum)

        for age in (
            timedelta(0),
            timedelta(seconds=-1),
            48,
            None,
        ):
            with self.subTest(age=age):
                with self.assertRaises(ValueError):
                    self.evaluate(maximum_collection_age=age)

        accepted = self.evaluate(
            self.movie(runtime_minutes=45),
            minimum_runtime=40,
            maximum_collection_age=timedelta(hours=2),
        )
        self.assertTrue(accepted.show_in_catalog)

        expired = self.evaluate(
            maximum_collection_age=timedelta(minutes=30),
        )
        self.assertFalse(expired.show_in_catalog)
        self.assertIn("stale_collection", expired.reasons)

    def test_ranking_uses_popularity_without_mutating_input(self):
        movies = [
            self.movie(movie_id="LOW", popularity=1),
            self.movie(movie_id="HIGH", popularity=100),
            self.movie(movie_id="MEDIUM", popularity=20),
        ]
        original = copy.deepcopy(movies)

        ranked = rank_catalog_movies(movies)

        self.assertEqual(
            [movie["movie_id"] for movie in ranked],
            ["HIGH", "MEDIUM", "LOW"],
        )
        self.assertEqual(movies, original)

    def test_ranking_ties_use_title_then_movie_id(self):
        movies = [
            self.movie(
                movie_id="B",
                title="Beta",
                popularity=10,
            ),
            self.movie(
                movie_id="A2",
                title="alfa",
                popularity=10,
            ),
            self.movie(
                movie_id="A1",
                title="Alfa",
                popularity=10,
            ),
        ]

        ranked = rank_catalog_movies(movies)

        self.assertEqual(
            [movie["movie_id"] for movie in ranked],
            ["A1", "A2", "B"],
        )

    def test_invalid_popularity_is_treated_as_zero(self):
        invalid_scores = (
            None,
            -1,
            "100",
            True,
            float("nan"),
            float("inf"),
            10**400,
        )

        for score in invalid_scores:
            with self.subTest(score=score):
                ranked = rank_catalog_movies([
                    self.movie(
                        movie_id="INVALID",
                        title="A",
                        popularity=score,
                    ),
                    self.movie(
                        movie_id="VALID",
                        title="Z",
                        popularity=1,
                    ),
                ])

                self.assertEqual(
                    ranked[0]["movie_id"],
                    "VALID",
                )

        without_score = self.movie(movie_id="NO-SCORE")
        del without_score["popularity"]

        ranked = rank_catalog_movies([
            without_score,
            self.movie(movie_id="VALID", popularity=1),
        ])
        self.assertEqual(ranked[0]["movie_id"], "VALID")

    def test_invalid_ranking_inputs_are_rejected(self):
        for movies in (None, {}, (), "filmes"):
            with self.subTest(movies=movies):
                with self.assertRaises(ValueError):
                    rank_catalog_movies(movies)

        invalid_movies = [
            None,
            {},
            self.movie(movie_id=""),
            self.movie(movie_id=123),
            self.movie(title="   "),
            self.movie(title=None),
        ]

        for movie in invalid_movies:
            with self.subTest(movie=movie):
                with self.assertRaises(ValueError):
                    rank_catalog_movies([movie])

        self.assertEqual(rank_catalog_movies([]), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
