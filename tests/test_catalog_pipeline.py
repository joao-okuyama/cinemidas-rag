"""Teste integrado: TMDB normalizado -> coleta persistida -> vitrine."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from src.booking.database import connect_database, initialize_database
from src.booking.public_catalog import list_public_catalog
from src.booking.tmdb_client import TMDBClient
from src.booking.tmdb_sync import sync_now_playing


class CatalogPipelineTests(unittest.TestCase):
    def test_successful_collection_feeds_public_and_bookable_catalogs(self):
        connection = connect_database(":memory:")
        self.addCleanup(connection.close)
        initialize_database(connection, seed_catalog=True)

        collected_at = datetime.now(timezone.utc).replace(microsecond=0)
        client = Mock(spec=TMDBClient)
        client.get_now_playing_page.return_value = {
            "page": 1,
            "total_pages": 1,
            "results": [{"id": 101}, {"id": 102}],
        }

        def details(movie_id):
            return {
                "id": movie_id,
                "title": f"Filme {movie_id}",
                "overview": "Sinopse disponível.",
                "runtime": 120 if movie_id == 101 else 30,
                "popularity": 80.0 if movie_id == 101 else 200.0,
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
                                    "release_date": "2026-09-01T00:00:00Z",
                                }
                            ],
                        }
                    ]
                },
            }

        client.get_movie_details.side_effect = details

        result = sync_now_playing(
            connection,
            client,
            collected_at=collected_at,
        )

        self.assertEqual(result.movies_processed, 2)
        self.assertEqual(
            connection.execute(
                "SELECT COUNT(*) FROM catalog_collections"
            ).fetchone()[0],
            1,
        )
        self.assertEqual(
            connection.execute(
                "SELECT COUNT(*) FROM catalog_collection_movies"
            ).fetchone()[0],
            2,
        )

        query_time = collected_at + timedelta(minutes=5)
        public_movies = list_public_catalog(
            connection,
            now=query_time,
        )

        self.assertEqual(
            [movie["movie_id"] for movie in public_movies],
            ["TMDB-101"],
        )
        self.assertFalse(public_movies[0]["show_session_options"])
        self.assertEqual(public_movies[0]["genres"], ["Ação"])
        self.assertTrue(public_movies[0]["poster_url"].endswith("/101.jpg"))

        starts_at = int((query_time + timedelta(hours=2)).timestamp())
        runtime_minutes = 120
        turnaround_minutes = 15
        ends_at = starts_at + runtime_minutes * 60
        room_available_at = ends_at + turnaround_minutes * 60

        connection.execute(
            """
            INSERT INTO sessions (
                session_id, movie_id, room_id, projection_format,
                audio_version, status, starts_at, runtime_minutes,
                turnaround_minutes, ends_at, room_available_at,
                full_price_cents, convenience_fee_cents
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "TEST-SESSION-101",
                "TMDB-101",
                "CV-ROOM-001",
                "2D",
                "DUBBED",
                "SCHEDULED",
                starts_at,
                runtime_minutes,
                turnaround_minutes,
                ends_at,
                room_available_at,
                3200,
                400,
            ),
        )
        connection.commit()

        bookable_movies = list_public_catalog(
            connection,
            now=query_time,
            only_bookable=True,
        )

        self.assertEqual(len(bookable_movies), 1)
        self.assertTrue(bookable_movies[0]["show_session_options"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
