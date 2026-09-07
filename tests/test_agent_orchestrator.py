"""Testes do limite entre linguagem natural e ações de reserva."""

import unittest
from datetime import datetime, timezone

from src.booking.agent_orchestrator import (
    BookingConversationAgent,
    safe_user_error,
    validate_decision,
)
from src.booking.agent_tools import BookingAgentTools
from src.booking.database import connect_database, initialize_database
from src.booking.normalized_movie_repository import save_normalized_collection
from src.booking.session_scheduler import generate_demo_sessions
from src.booking.tmdb_normalizer import normalize_tmdb_movie


class AgentOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
        self.connection = connect_database(":memory:")
        self.addCleanup(self.connection.close)
        initialize_database(self.connection, seed_catalog=True)

        movie = normalize_tmdb_movie(
            {
                "id": 101,
                "title": "Aventura de teste",
                "overview": "Uma aventura segura para testes.",
                "runtime": 120,
                "popularity": 90.0,
                "poster_path": "/101.jpg",
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
            collected_at=self.now,
        )
        save_normalized_collection(
            self.connection,
            [movie],
            collection_id="TEST-COLLECTION",
            collected_at=int(self.now.timestamp()),
            finished_at=int(self.now.timestamp()),
            pages_fetched=1,
            duplicate_ids=0,
        )
        generate_demo_sessions(
            self.connection,
            now=self.now,
            days=1,
            max_movies=1,
            sessions_per_room_day=1,
        )
        self.tools = BookingAgentTools(
            self.connection,
            user_id="USER-1",
            conversation_id="CONVERSATION-1",
            now=self.now,
        )

    def agent_for(self, decision):
        return BookingConversationAgent(
            self.tools,
            lambda _message, _context: decision,
            now=self.now,
        )

    def test_catalog_action_returns_rich_movie_payload(self):
        turn = self.agent_for(
            {
                "action": "catalog",
                "arguments": {"genre": "Ação", "limit": 5},
                "reply": "Temos esta opção:",
            }
        ).handle("Quero um filme de ação")

        self.assertEqual(turn.view, "catalog")
        self.assertEqual(turn.payload[0]["movie_id"], "TMDB-101")
        self.assertEqual(
            turn.payload[0]["poster_url"],
            "https://image.tmdb.org/t/p/w500/101.jpg",
        )
        self.assertIn("Aventura de teste", turn.text)

    def test_model_cannot_inject_unapproved_payment_arguments(self):
        with self.assertRaisesRegex(ValueError, "não permitidos"):
            validate_decision(
                {
                    "action": "pay",
                    "arguments": {
                        "method": "PIX_MOCK",
                        "succeed": True,
                    },
                }
            )

    def test_first_session_is_selected_without_calling_model(self):
        self.tools.select_movie("TMDB-101", now=self.now)
        expected = self.tools.sessions(now=self.now, limit=12)[0]
        self.tools.remember_options("sessions", self.tools.sessions(now=self.now, limit=12))

        def forbidden_planner(_message, _context):
            self.fail("O modelo não deve resolver uma opção ordinal simples.")

        agent = BookingConversationAgent(
            self.tools,
            forbidden_planner,
            now=self.now,
        )
        turn = agent.handle("Quero o primeiro")

        self.assertEqual(turn.view, "seat_map")
        self.assertEqual(
            self.tools.state()["selected_session_id"],
            expected["session_id"],
        )
        self.assertIn("Hoje", turn.text)
        self.assertNotIn("T13:00", turn.text)

    def test_known_errors_are_specific_and_unknown_errors_are_hidden(self):
        self.assertEqual(
            safe_user_error(ValueError("Reserve os assentos primeiro.")),
            "Reserve os assentos primeiro.",
        )
        self.assertNotIn(
            "segredo interno",
            safe_user_error(RuntimeError("segredo interno")),
        )

    def test_payment_requires_explicit_user_confirmation(self):
        self.tools.select_movie("TMDB-101", now=self.now)
        session = self.tools.sessions(now=self.now)[0]
        self.tools.select_session(session["session_id"], now=self.now)
        self.tools.hold_seats(["F6"], now=self.now)
        order = self.tools.checkout({"F6": "FULL"}, now=self.now)

        decision = {
            "action": "pay",
            "arguments": {"method": "PIX_MOCK"},
            "reply": "",
        }
        agent = self.agent_for(decision)

        refused = agent.handle("Pode continuar")
        self.assertEqual(refused.view, "confirmation_required")
        self.assertEqual(
            self.tools.state()["state"],
            "AWAITING_PAYMENT",
        )

        confirmed = agent.handle("Confirmo o pagamento com PIX")
        self.assertEqual(confirmed.view, "voucher")
        self.assertIn("SIMULAÇÃO — SEM VALIDADE", confirmed.text)
        self.assertEqual(self.tools.state()["state"], "CONFIRMED")
        self.assertEqual(
            self.tools.recent_orders()[0]["order_id"],
            order["order_id"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
