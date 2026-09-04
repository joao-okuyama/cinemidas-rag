"""Teste integrado da programação simulada CineViva."""

import unittest
from datetime import datetime, timezone

from src.booking.database import connect_database, initialize_database
from src.booking.normalized_movie_repository import (
    save_normalized_collection,
)
from src.booking.public_catalog import list_public_catalog
from src.booking.session_scheduler import (
    generate_demo_sessions,
    list_session_options,
)
from src.booking.tmdb_normalizer import normalize_tmdb_movie


class SessionSchedulerTests(unittest.TestCase):
    def test_catalog_is_scheduled_once_and_exposed_for_booking(self):
        connection = connect_database(":memory:")
        self.addCleanup(connection.close)
        initialize_database(connection, seed_catalog=True)

        now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
        movies = []

        for movie_id, runtime, popularity in (
            (101, 100, 90.0),
            (102, 120, 80.0),
            (103, 140, 70.0),
        ):
            movies.append(
                normalize_tmdb_movie(
                    {
                        "id": movie_id,
                        "title": f"Filme {movie_id}",
                        "overview": "Sinopse disponível.",
                        "runtime": runtime,
                        "popularity": popularity,
                        "poster_path": f"/{movie_id}.jpg",
                        "genres": [{"id": 28, "name": "Ação"}],
                        "release_dates": {
                            "results": [
                                {
                                    "iso_3166_1": "BR",
                                    "release_dates": [
                                        {
                                            "type": 3,
                                            "certification": "12",
                                            "release_date": (
                                                "2026-09-01T00:00:00Z"
                                            ),
                                        }
                                    ],
                                }
                            ]
                        },
                    },
                    collected_at=now,
                )
            )

        save_normalized_collection(
            connection,
            movies,
            collection_id="TEST-COLLECTION",
            collected_at=int(now.timestamp()),
            finished_at=int(now.timestamp()),
            pages_fetched=1,
            duplicate_ids=0,
        )

        result = generate_demo_sessions(
            connection,
            now=now,
            days=2,
            max_movies=3,
            sessions_per_room_day=2,
        )

        self.assertEqual(result.created_sessions, 24)
        self.assertEqual(result.scheduled_movies, 3)

        options = list_session_options(connection, now=now)
        self.assertEqual(len(options), 24)
        self.assertTrue(
            all(option["starts_at"] < option["ends_at"] for option in options)
        )
        self.assertTrue(
            all(
                option["total_full_price_cents"]
                == option["full_price_cents"]
                + option["convenience_fee_cents"]
                for option in options
            )
        )

        intervals_by_room = {}
        for row in connection.execute(
            """
            SELECT room_id, starts_at, room_available_at
            FROM sessions
            ORDER BY room_id, starts_at
            """
        ):
            previous_end = intervals_by_room.get(row["room_id"])
            if previous_end is not None:
                self.assertGreaterEqual(row["starts_at"], previous_end)
            intervals_by_room[row["room_id"]] = row["room_available_at"]

        repeated = generate_demo_sessions(
            connection,
            now=now,
            days=2,
            max_movies=3,
            sessions_per_room_day=2,
        )
        self.assertEqual(repeated.created_sessions, 0)
        self.assertEqual(repeated.existing_future_sessions, 24)

        bookable = list_public_catalog(
            connection,
            now=now,
            only_bookable=True,
        )
        self.assertEqual(len(bookable), 3)
        self.assertTrue(
            all(movie["show_session_options"] for movie in bookable)
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
