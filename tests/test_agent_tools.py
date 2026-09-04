"""Teste integrado do fluxo determinístico exposto ao agente."""

import unittest
from datetime import datetime, timezone

from src.booking.agent_tools import BookingAgentTools
from src.booking.database import connect_database, initialize_database
from src.booking.normalized_movie_repository import save_normalized_collection
from src.booking.session_scheduler import generate_demo_sessions
from src.booking.tmdb_normalizer import normalize_tmdb_movie


class AgentToolsTests(unittest.TestCase):
    def test_complete_conversation_flow_is_persisted_and_private(self):
        connection = connect_database(":memory:")
        self.addCleanup(connection.close)
        initialize_database(connection, seed_catalog=True)

        now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
        movies = []

        for movie_id, title, genre_id, genre, popularity in (
            (101, "Aventura de teste", 28, "Ação", 90.0),
            (102, "Comédia de teste", 35, "Comédia", 80.0),
        ):
            movies.append(
                normalize_tmdb_movie(
                    {
                        "id": movie_id,
                        "title": title,
                        "overview": "Sinopse disponível.",
                        "runtime": 120,
                        "popularity": popularity,
                        "poster_path": f"/{movie_id}.jpg",
                        "genres": [{"id": genre_id, "name": genre}],
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
        generate_demo_sessions(
            connection,
            now=now,
            days=2,
            max_movies=2,
            sessions_per_room_day=2,
        )

        tools = BookingAgentTools(
            connection,
            user_id="USER-1",
            conversation_id="CONVERSATION-1",
            now=now,
        )

        action_movies = tools.catalog(genre="Ação", now=now)
        self.assertEqual(len(action_movies), 1)
        self.assertEqual(action_movies[0]["movie_id"], "TMDB-101")

        tools.select_movie("TMDB-101", now=now)
        sessions = tools.sessions(now=now)
        self.assertTrue(sessions)
        selected_session = sessions[0]
        tools.select_session(selected_session["session_id"], now=now)

        seat_map = tools.seat_map(now=now)
        self.assertEqual(len(seat_map["seats"]), 120)
        self.assertIn("TELA", seat_map["text"])

        hold = tools.hold_seats(["F6", "F7"], now=now)
        self.assertEqual(hold["seat_labels"], ["F6", "F7"])

        order = tools.checkout(
            {"F6": "FULL", "F7": "HALF"},
            now=now,
        )
        self.assertEqual(order["status"], "AWAITING_PAYMENT")

        payment = tools.pay(
            "PIX_MOCK",
            "AGENT-FLOW-PAYMENT-1",
            now=now,
        )
        self.assertEqual(payment["status"], "SUCCEEDED")
        self.assertIsNotNone(payment["booking_code"])
        self.assertEqual(tools.state()["state"], "CONFIRMED")
        self.assertIn("SIMULAÇÃO — SEM VALIDADE", tools.voucher())

        restored = BookingAgentTools(
            connection,
            user_id="USER-1",
            conversation_id="CONVERSATION-1",
            now=now,
        )
        self.assertEqual(restored.state()["state"], "CONFIRMED")
        self.assertEqual(len(restored.recent_orders()), 1)

        with self.assertRaisesRegex(ValueError, "autenticado"):
            BookingAgentTools(
                connection,
                user_id="USER-2",
                conversation_id="CONVERSATION-1",
                now=now,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
