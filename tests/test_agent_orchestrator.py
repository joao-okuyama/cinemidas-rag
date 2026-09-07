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

    # ── Regression: Bug #1 — questions must NOT confirm payment ──

    def test_question_about_payment_does_not_confirm(self):
        """Mensagens interrogativas sobre pagamento não devem disparar pay."""
        questions = [
            "Como funciona o pagamento com PIX?",
            "Se eu confirmar o pagamento com PIX, o que acontece?",
            "Qual o prazo de pagamento?",
            "Quanto custa o pagamento com cartão?",
            "O que é pagamento com pontos?",
        ]
        for question in questions:
            with self.subTest(question=question):
                self.assertFalse(
                    BookingConversationAgent._payment_confirmed(question),
                    f"Should NOT confirm: {question!r}",
                )

    def test_deferred_payment_does_not_confirm(self):
        """Frases com intenção futura ou condicional NÃO são confirmação."""
        deferred = [
            "Vou pagar com PIX amanhã",
            "Antes de pagar com PIX, preciso conferir os assentos.",
        ]
        for msg in deferred:
            with self.subTest(msg=msg):
                self.assertFalse(
                    BookingConversationAgent._payment_confirmed(msg),
                    f"Should NOT confirm: {msg!r}",
                )

    def test_explicit_confirmation_still_works(self):
        """Confirmações explícitas e legítimas devem continuar funcionando."""
        confirmations = [
            "Confirmo o pagamento com PIX",
            "Pode pagar com cartão",
            "Pagar com pix",
            "Confirmar pagamento",
            "Quero pagar com pontos",
            "Finalizar com pix",
        ]
        for msg in confirmations:
            with self.subTest(msg=msg):
                self.assertTrue(
                    BookingConversationAgent._payment_confirmed(msg),
                    f"Should confirm: {msg!r}",
                )

    # ── Regression: Bug #2 — inteira/meia parsed individually ──

    def _setup_held_seats(self, labels):
        """Helper: set up movie → session → held seats, return agent."""
        self.tools.select_movie("TMDB-101", now=self.now)
        session = self.tools.sessions(now=self.now)[0]
        self.tools.select_session(session["session_id"], now=self.now)
        self.tools.hold_seats(labels, now=self.now)

        def forbidden_planner(_message, _context):
            self.fail("The model should not be called for deterministic shortcuts.")

        return BookingConversationAgent(
            self.tools, forbidden_planner, now=self.now,
        )

    def _setup_session_selected(self):
        """Helper: set up movie → session (no held seats), return agent."""
        self.tools.select_movie("TMDB-101", now=self.now)
        session = self.tools.sessions(now=self.now)[0]
        self.tools.select_session(session["session_id"], now=self.now)

        def forbidden_planner(_message, _context):
            self.fail("The model should not be called for deterministic shortcuts.")

        return BookingConversationAgent(
            self.tools, forbidden_planner, now=self.now,
        )

    def test_f6_inteira_f7_meia_from_session_selected(self):
        """In SESSION_SELECTED state, 'F6 inteira e F7 meia' must pass correct half_price_seats."""
        agent = self._setup_session_selected()
        decision = agent.decide("F6 inteira e F7 meia")
        self.assertEqual(decision["action"], "continue_to_checkout")
        args = decision["arguments"]
        self.assertIn("F6", args["seat_labels"])
        self.assertIn("F7", args["seat_labels"])
        # F7 is meia, F6 is not
        self.assertIn("F7", args["half_price_seats"])
        self.assertNotIn("F6", args["half_price_seats"])

    def test_f6_inteira_e_f7_meia_parsed_correctly(self):
        agent = self._setup_held_seats(["F6", "F7"])
        decision = agent.decide("F6 inteira e F7 meia")
        self.assertEqual(decision["action"], "checkout")
        types = decision["arguments"]["ticket_types"]
        self.assertEqual(types["F6"], "FULL")
        self.assertEqual(types["F7"], "HALF")

    def test_f6_e_f7_inteira_all_same_type(self):
        agent = self._setup_held_seats(["F6", "F7"])
        decision = agent.decide("F6 e F7 inteira")
        self.assertEqual(decision["action"], "checkout")
        types = decision["arguments"]["ticket_types"]
        self.assertEqual(types["F6"], "FULL")
        self.assertEqual(types["F7"], "FULL")

    # ── Regression: Bug #3 — "todos inteira/meia" must not crash ──

    def test_todos_inteira_uses_correct_query(self):
        agent = self._setup_held_seats(["F6", "F7"])
        decision = agent.decide("Todos inteira")
        self.assertEqual(decision["action"], "checkout")
        types = decision["arguments"]["ticket_types"]
        self.assertEqual(len(types), 2)
        for label in types.values():
            self.assertEqual(label, "FULL")

    def test_todos_meia_uses_correct_query(self):
        agent = self._setup_held_seats(["G3"])
        decision = agent.decide("tudo meia")
        self.assertEqual(decision["action"], "checkout")
        types = decision["arguments"]["ticket_types"]
        self.assertEqual(len(types), 1)
        for label in types.values():
            self.assertEqual(label, "HALF")

    # ── Regression: Bug #4 — _context() with session records in displayed_items ──

    def test_context_does_not_crash_with_session_displayed_items(self):
        """When displayed_items contains session records (movie_title not title),
        _context() must not raise KeyError."""
        self.tools.select_movie("TMDB-101", now=self.now)
        sessions = self.tools.sessions(now=self.now, limit=3)
        self.tools.remember_options("sessions", sessions)

        agent = BookingConversationAgent(
            self.tools,
            lambda _m, _c: {"action": "help", "arguments": {}, "reply": "ok"},
            now=self.now,
        )
        # This should NOT raise KeyError: 'title'
        context = agent._context()
        self.assertIn("catalog", context)
        for movie in context["catalog"]:
            self.assertIn("title", movie)
            self.assertIn("movie_id", movie)

    # ── Regression: Informational payment queries must not confirm ──

    def test_informational_payment_query_does_not_confirm(self):
        """'Quero entender o botão de confirmar pagamento com PIX' não é confirmação."""
        informational = [
            "Quero entender o botão de confirmar pagamento com PIX.",
            "Quero saber o botão de confirmar pagamento com PIX.",
            "Explique o pagamento com PIX.",
            "Tenho dúvida sobre o botão de confirmar pagamento.",
            "Como funciona o botão de pagar com PIX?",
            "O botão de confirmar pagamento com PIX sumiu da tela.",
        ]
        for msg in informational:
            with self.subTest(msg=msg):
                self.assertFalse(
                    BookingConversationAgent._payment_confirmed(msg),
                    f"Should NOT confirm: {msg!r}",
                )

    def test_informational_payment_query_preserves_awaiting_payment_state(self):
        """No estado AWAITING_PAYMENT, mensagem informativa não gera voucher nem altera estado."""
        self.tools.select_movie("TMDB-101", now=self.now)
        session = self.tools.sessions(now=self.now)[0]
        self.tools.select_session(session["session_id"], now=self.now)
        self.tools.hold_seats(["F6"], now=self.now)
        self.tools.checkout({"F6": "FULL"}, now=self.now)

        agent = BookingConversationAgent(
            self.tools,
            lambda _m, _c: {
                "action": "help",
                "arguments": {},
                "reply": "O botão de confirmação serve para concluir a reserva simulada.",
            },
            now=self.now,
        )

        msg = "Quero entender o botão de confirmar pagamento com PIX."
        turn = agent.handle(msg)
        self.assertEqual(self.tools.state()["state"], "AWAITING_PAYMENT")
        self.assertNotEqual(turn.view, "voucher")
        self.assertEqual(turn.view, "message")
        # Ensure no payment was registered in the database
        payments = self.connection.execute("SELECT * FROM payments").fetchall()
        self.assertEqual(len(payments), 0)

    # ── Regression: Ambiguous ticket types (e.g. 3 seats, 2 types) ──

    def test_ambiguous_types_in_session_selected_holds_seats_without_pricing(self):
        """'F6, F7 e F8: inteira e meia' em SESSION_SELECTED deve reservar assentos sem precificar."""
        agent = self._setup_session_selected()
        msg = "F6, F7 e F8: inteira e meia"
        turn = agent.handle(msg)

        # Expected: holds seats temporarily, asks for clarification, does NOT price
        self.assertEqual(turn.view, "hold")
        self.assertEqual(self.tools.state()["state"], "SEATS_HELD")
        self.assertIn("F6, F7, F8", turn.text)

        # Verify no orders or order_items were created
        order_items = self.connection.execute("SELECT * FROM order_items").fetchall()
        self.assertEqual(len(order_items), 0)
        orders = self.connection.execute("SELECT * FROM orders").fetchall()
        self.assertEqual(len(orders), 0)

    def test_ambiguous_types_in_seats_held_asks_clarification(self):
        """'F6, F7 e F8: inteira e meia' em SEATS_HELD deve pedir esclarecimento."""
        agent = self._setup_held_seats(["F6", "F7", "F8"])
        decision = agent.decide("F6, F7 e F8: inteira e meia")
        self.assertEqual(decision["action"], "help")
        self.assertIn("especifique", decision["reply"].casefold())
        self.assertEqual(self.tools.state()["state"], "SEATS_HELD")

    # ── Regression: Full flow with types, pricing and authorization ──

    def test_full_booking_flow_types_pricing_and_authorization(self):
        """Fluxo completo: seleção -> inteira/meia -> checkout -> dúvida (sem pagar) -> autorização."""
        agent = self._setup_session_selected()

        # Step 1: Select seats with mixed types
        turn_checkout = agent.handle("F6 inteira e F7 meia")
        self.assertEqual(turn_checkout.view, "checkout")
        self.assertEqual(self.tools.state()["state"], "AWAITING_PAYMENT")

        # Verify ticket types in DB
        rows = self.connection.execute(
            """
            SELECT s.row_label || s.seat_number AS seat, oi.ticket_type
            FROM order_items oi
            JOIN seats s ON s.seat_id = oi.seat_id
            ORDER BY s.seat_number
            """
        ).fetchall()
        types_map = {r["seat"]: r["ticket_type"] for r in rows}
        self.assertEqual(types_map["F6"], "FULL")
        self.assertEqual(types_map["F7"], "HALF")

        # Step 2: Informational question — must NOT confirm payment
        agent_info = BookingConversationAgent(
            self.tools,
            lambda _m, _c: {
                "action": "help",
                "arguments": {},
                "reply": "O PIX é simulado e instantâneo.",
            },
            now=self.now,
        )
        turn_info = agent_info.handle("Quero entender o botão de confirmar pagamento com PIX.")
        self.assertEqual(self.tools.state()["state"], "AWAITING_PAYMENT")
        self.assertNotEqual(turn_info.view, "voucher")
        self.assertEqual(len(self.connection.execute("SELECT * FROM payments").fetchall()), 0)

        # Step 3: Explicit authorization — must confirm and generate voucher
        turn_confirm = agent_info.handle("Confirmo o pagamento com PIX")
        self.assertEqual(turn_confirm.view, "voucher")
        self.assertEqual(self.tools.state()["state"], "CONFIRMED")
        payments = self.connection.execute("SELECT * FROM payments").fetchall()
        self.assertEqual(len(payments), 1)
        self.assertEqual(payments[0]["method"], "PIX_MOCK")
        self.assertEqual(payments[0]["status"], "SUCCEEDED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
