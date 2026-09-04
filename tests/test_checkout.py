"""Teste integrado do checkout e pagamento simulados."""

import unittest
from datetime import datetime, timedelta, timezone

from src.booking.checkout import (
    create_order,
    get_order,
    list_user_orders,
    pay_order,
    render_voucher,
)
from src.booking.database import connect_database, initialize_database
from src.booking.seat_holds import create_seat_hold


class CheckoutTests(unittest.TestCase):
    def test_checkout_is_priced_confirmed_idempotent_and_private(self):
        connection = connect_database(":memory:")
        self.addCleanup(connection.close)
        initialize_database(connection, seed_catalog=True)

        now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
        starts_at = int((now + timedelta(hours=3)).timestamp())
        runtime = 120
        turnaround = 15
        ends_at = starts_at + runtime * 60

        connection.execute(
            """
            INSERT INTO movies (movie_id, title, runtime_minutes)
            VALUES ('TEST-MOVIE', 'Filme original', ?)
            """,
            (runtime,),
        )
        connection.execute(
            """
            INSERT INTO sessions (
                session_id, movie_id, room_id, projection_format,
                audio_version, status, starts_at, runtime_minutes,
                turnaround_minutes, ends_at, room_available_at,
                full_price_cents, convenience_fee_cents
            )
            VALUES (
                'TEST-SESSION', 'TEST-MOVIE', 'CV-ROOM-001', '2D',
                'DUBBED', 'SCHEDULED', ?, ?, ?, ?, ?, 3200, 400
            )
            """,
            (
                starts_at,
                runtime,
                turnaround,
                ends_at,
                ends_at + turnaround * 60,
            ),
        )
        connection.commit()

        hold = create_seat_hold(
            connection,
            user_id="USER-1",
            session_id="TEST-SESSION",
            seat_labels=["F6", "F7"],
            now=now,
        )

        order = create_order(
            connection,
            user_id="USER-1",
            hold_id=hold.hold_id,
            ticket_types={"F6": "FULL", "F7": "HALF"},
            now=now,
        )

        self.assertEqual(order["status"], "AWAITING_PAYMENT")
        self.assertEqual(order["subtotal_cents"], 6400)
        self.assertEqual(order["discount_cents"], 1600)
        self.assertEqual(order["fee_cents"], 800)
        self.assertEqual(order["total_cents"], 5600)

        repeated_order = create_order(
            connection,
            user_id="USER-1",
            hold_id=hold.hold_id,
            ticket_types={"F6": "FULL", "F7": "HALF"},
            now=now,
        )
        self.assertEqual(repeated_order["order_id"], order["order_id"])

        payment = pay_order(
            connection,
            user_id="USER-1",
            order_id=order["order_id"],
            method="PIX_MOCK",
            idempotency_key="TEST-PAYMENT-1",
            now=now,
        )
        self.assertEqual(payment.status, "SUCCEEDED")
        self.assertEqual(payment.amount_cents, 5600)
        self.assertIsNotNone(payment.booking_code)

        repeated_payment = pay_order(
            connection,
            user_id="USER-1",
            order_id=order["order_id"],
            method="PIX_MOCK",
            idempotency_key="TEST-PAYMENT-1",
            now=now,
        )
        self.assertEqual(repeated_payment.payment_id, payment.payment_id)
        self.assertEqual(
            connection.execute(
                "SELECT COUNT(*) FROM payments"
            ).fetchone()[0],
            1,
        )

        confirmed = get_order(
            connection,
            order_id=order["order_id"],
            user_id="USER-1",
        )
        self.assertEqual(confirmed["status"], "CONFIRMED")
        self.assertTrue(
            all(item["ticket_code"] for item in confirmed["items"])
        )
        self.assertEqual(
            connection.execute(
                """
                SELECT COUNT(*) FROM session_seats
                WHERE order_id = ? AND status = 'BOOKED'
                """,
                (order["order_id"],),
            ).fetchone()[0],
            2,
        )

        with self.assertRaisesRegex(ValueError, "este usuário"):
            get_order(
                connection,
                order_id=order["order_id"],
                user_id="USER-2",
            )

        connection.execute(
            "UPDATE movies SET title = 'Título alterado'"
        )
        connection.execute(
            "UPDATE cinemas SET name = 'Cinema alterado'"
        )
        connection.commit()

        history = list_user_orders(connection, user_id="USER-1")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["movie_title"], "Filme original")
        self.assertEqual(history[0]["cinema_name"], "CineViva Centro")

        voucher = render_voucher(history[0])
        self.assertIn("SIMULAÇÃO — SEM VALIDADE", voucher)
        self.assertIn(payment.booking_code, voucher)
        self.assertIn("F6, F7", voucher)


if __name__ == "__main__":
    unittest.main(verbosity=2)
