"""Teste integrado da API consumida pelo futuro front-end."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from src.booking.database import connect_database, initialize_database
from src.booking.http_api import create_booking_api
from src.booking.normalized_movie_repository import save_normalized_collection
from src.booking.session_scheduler import generate_demo_sessions
from src.booking.tmdb_normalizer import normalize_tmdb_movie


class HttpApiTests(unittest.TestCase):
    def test_complete_frontend_journey(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        database_path = Path(temporary.name) / "api.db"
        connection = connect_database(database_path)
        self.addCleanup(connection.close)
        initialize_database(connection, seed_catalog=True)

        now = datetime.now(timezone.utc)
        release_date = (now - timedelta(days=2)).strftime(
            "%Y-%m-%dT00:00:00Z"
        )
        movie = normalize_tmdb_movie(
            {
                "id": 701,
                "title": "Filme da API",
                "overview": "Sinopse disponível.",
                "runtime": 115,
                "popularity": 99.0,
                "poster_path": "/701.jpg",
                "genres": [{"id": 28, "name": "Ação"}],
                "release_dates": {
                    "results": [
                        {
                            "iso_3166_1": "BR",
                            "release_dates": [
                                {
                                    "type": 3,
                                    "certification": "12",
                                    "release_date": release_date,
                                }
                            ],
                        }
                    ]
                },
            },
            collected_at=now,
        )
        save_normalized_collection(
            connection,
            [movie],
            collection_id="API-TEST",
            collected_at=int(now.timestamp()),
            finished_at=int(now.timestamp()),
            pages_fetched=1,
            duplicate_ids=0,
        )
        generate_demo_sessions(
            connection,
            now=now,
            days=2,
            max_movies=1,
            sessions_per_room_day=1,
        )
        connection.close()

        client = TestClient(create_booking_api(database_path, catalog_movies=1))

        health = client.get("/api/v1/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["payments"], "simulated_only")

        catalog = client.get("/api/v1/catalog").json()["items"]
        self.assertEqual(catalog[0]["movie_id"], "TMDB-701")

        sessions = client.get(
            "/api/v1/movies/TMDB-701/sessions"
        ).json()["items"]
        self.assertTrue(sessions)
        session_id = sessions[0]["session_id"]

        seats = client.get(
            f"/api/v1/sessions/{session_id}/seats"
        ).json()
        self.assertEqual(len(seats["items"]), 120)

        checkout = client.post(
            "/api/v1/checkout",
            json={
                "user_id": "WEB-USER-API",
                "conversation_id": "WEB-CONV-API",
                "movie_id": "TMDB-701",
                "session_id": session_id,
                "seat_labels": ["F6", "F7"],
                "half_price_seats": ["F7"],
            },
        )
        self.assertEqual(checkout.status_code, 200)
        order = checkout.json()["order"]
        self.assertEqual(order["status"], "AWAITING_PAYMENT")
        self.assertGreater(order["discount_cents"], 0)

        payment = client.post(
            f"/api/v1/orders/{order['order_id']}/payments",
            json={
                "user_id": "WEB-USER-API",
                "method": "PIX_MOCK",
                "idempotency_key": "FRONTEND-TEST-PAYMENT-1",
            },
        )
        self.assertEqual(payment.status_code, 200)
        self.assertEqual(payment.json()["payment"]["status"], "SUCCEEDED")
        self.assertIn("SIMULAÇÃO — SEM VALIDADE", payment.json()["voucher"])

        orders = client.get(
            "/api/v1/users/WEB-USER-API/orders"
        ).json()["items"]
        self.assertEqual(len(orders), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
