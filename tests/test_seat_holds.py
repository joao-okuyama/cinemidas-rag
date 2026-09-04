"""Teste integrado da reserva temporária de assentos."""

import unittest
from datetime import datetime, timedelta, timezone

from src.booking.database import connect_database, initialize_database
from src.booking.seat_holds import (
    SeatUnavailableError,
    create_seat_hold,
    get_seat_map,
    release_hold,
    render_text_seat_map,
)


class SeatHoldTests(unittest.TestCase):
    def test_group_hold_is_atomic_private_expiring_and_releasable(self):
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
            VALUES ('TEST-MOVIE', 'Filme de teste', ?)
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

        first = create_seat_hold(
            connection,
            user_id="USER-1",
            session_id="TEST-SESSION",
            seat_labels=["F6", "F7"],
            now=now,
        )

        self.assertEqual(first.seat_labels, ("F6", "F7"))
        self.assertEqual(first.expires_at - first.created_at, 300)

        own_map = get_seat_map(
            connection,
            session_id="TEST-SESSION",
            user_id="USER-1",
            now=now,
        )
        other_map = get_seat_map(
            connection,
            session_id="TEST-SESSION",
            user_id="USER-2",
            now=now,
        )

        own_status = {seat["label"]: seat["status"] for seat in own_map}
        other_status = {
            seat["label"]: seat["status"] for seat in other_map
        }
        self.assertEqual(len(own_map), 120)
        self.assertEqual(own_status["F6"], "SELECTED")
        self.assertEqual(other_status["F6"], "OCCUPIED")

        with self.assertRaises(SeatUnavailableError):
            create_seat_hold(
                connection,
                user_id="USER-2",
                session_id="TEST-SESSION",
                seat_labels=["F7", "F8"],
                now=now,
            )

        after_failure = get_seat_map(
            connection,
            session_id="TEST-SESSION",
            user_id="USER-2",
            now=now,
        )
        after_status = {
            seat["label"]: seat["status"] for seat in after_failure
        }
        self.assertEqual(after_status["F7"], "OCCUPIED")
        self.assertEqual(after_status["F8"], "AVAILABLE")

        after_expiration = now + timedelta(seconds=301)
        second = create_seat_hold(
            connection,
            user_id="USER-2",
            session_id="TEST-SESSION",
            seat_labels=["F6", "F7"],
            now=after_expiration,
        )
        self.assertNotEqual(second.hold_id, first.hold_id)

        first_status = connection.execute(
            "SELECT status FROM seat_holds WHERE hold_id = ?",
            (first.hold_id,),
        ).fetchone()["status"]
        self.assertEqual(first_status, "EXPIRED")

        rendered = render_text_seat_map(
            get_seat_map(
                connection,
                session_id="TEST-SESSION",
                user_id="USER-2",
                now=after_expiration,
            )
        )
        self.assertIn("TELA", rendered)
        self.assertIn("●06", rendered)

        self.assertTrue(
            release_hold(
                connection,
                hold_id=second.hold_id,
                user_id="USER-2",
                now=after_expiration,
            )
        )
        self.assertFalse(
            release_hold(
                connection,
                hold_id=second.hold_id,
                user_id="USER-2",
                now=after_expiration,
            )
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
