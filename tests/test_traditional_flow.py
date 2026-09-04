"""Teste integrado único da jornada de compra tradicional."""

import unittest
from datetime import datetime, timezone

from src.booking.agent_tools import BookingAgentTools
from src.booking.database import connect_database, initialize_database
from src.booking.normalized_movie_repository import save_normalized_collection
from src.booking.session_scheduler import generate_demo_sessions
from src.booking.tmdb_normalizer import normalize_tmdb_movie
from src.booking.traditional_flow import TraditionalBookingFlow


class TraditionalFlowTests(unittest.TestCase):
    def test_complete_click_journey_uses_shared_booking_engine(self):
        connection = connect_database(":memory:")
        self.addCleanup(connection.close)
        initialize_database(connection, seed_catalog=True)

        now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
        movie = normalize_tmdb_movie(
            {
                "id": 501,
                "title": "Filme da compra tradicional",
                "overview": "Sinopse disponível.",
                "runtime": 110,
                "popularity": 95.0,
                "poster_path": "/501.jpg",
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
            },
            collected_at=now,
        )
        save_normalized_collection(
            connection,
            [movie],
            collection_id="TRADITIONAL-TEST",
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

        tools = BookingAgentTools(
            connection,
            user_id="SHARED-USER",
            conversation_id="TRADITIONAL-CONVERSATION",
            now=now,
        )
        flow = TraditionalBookingFlow(tools)

        selected = flow.choose_movie("TMDB-501")
        self.assertTrue(selected["sessions"])
        seats = flow.choose_session(
            selected["sessions"][0]["session_id"]
        )
        self.assertIn("F6", seats["available_seats"])
        self.assertIn("TELA", seats["seat_map"])

        checkout = flow.continue_to_checkout(["F6", "F7"], ["F7"])
        self.assertEqual(checkout["hold"]["seat_labels"], ["F6", "F7"])
        order = checkout["order"]
        self.assertEqual(order["status"], "AWAITING_PAYMENT")
        self.assertGreater(order["discount_cents"], 0)

        result = flow.pay("PIX_MOCK")
        self.assertEqual(result["payment"]["status"], "SUCCEEDED")
        self.assertIn("SIMULAÇÃO — SEM VALIDADE", result["voucher"])

        ai_tools = BookingAgentTools(
            connection,
            user_id="SHARED-USER",
            conversation_id="AI-CONVERSATION",
            now=now,
        )
        self.assertEqual(len(ai_tools.recent_orders()), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
