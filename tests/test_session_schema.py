import sqlite3
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BOOKING_DIRECTORY = PROJECT_ROOT / "src" / "booking"

# Fixed UTC timestamp for reproducible tests.
# Historical sessions are permitted by the database.
BASE_START = 1700000000


class SessionSchemaTests(unittest.TestCase):
    """Valida sessões sem usar APIs ou alterar a aplicação publicada."""

    @classmethod
    def setUpClass(cls):
        cls.catalog_schema = (
            BOOKING_DIRECTORY / "schema.sql"
        ).read_text(encoding="utf-8")

        cls.catalog_seed = (
            BOOKING_DIRECTORY / "seed_catalog.sql"
        ).read_text(encoding="utf-8")

        cls.session_schema = (
            BOOKING_DIRECTORY / "session_schema.sql"
        ).read_text(encoding="utf-8")

    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.addCleanup(self.connection.close)

        self.connection.executescript(self.catalog_schema)
        self.connection.executescript(self.catalog_seed)
        self.connection.executescript(self.session_schema)

        self.connection.execute("""
            INSERT INTO movies (
                movie_id, title, runtime_minutes
            ) VALUES (
                'TEST-MOVIE-001', 'Filme de Teste', 120
            )
        """)
        self.connection.commit()

    def insert_session(self, **overrides):
        values = {
            "session_id": "TEST-SESSION-001",
            "movie_id": "TEST-MOVIE-001",
            "room_id": "CV-ROOM-001",
            "projection_format": "2D",
            "audio_version": "SUBTITLED",
            "status": "SCHEDULED",
            "starts_at": BASE_START,
            "runtime_minutes": 120,
            "turnaround_minutes": 20,
            "full_price_cents": 3200,
            "convenience_fee_cents": 300,
        }

        values.update(overrides)

        values.setdefault(
            "ends_at",
            values["starts_at"] + values["runtime_minutes"] * 60,
        )

        values.setdefault(
            "room_available_at",
            values["ends_at"] + values["turnaround_minutes"] * 60,
        )

        self.connection.execute("""
            INSERT INTO sessions (
                session_id,
                movie_id,
                room_id,
                projection_format,
                audio_version,
                status,
                starts_at,
                runtime_minutes,
                turnaround_minutes,
                ends_at,
                room_available_at,
                full_price_cents,
                convenience_fee_cents
            ) VALUES (
                :session_id,
                :movie_id,
                :room_id,
                :projection_format,
                :audio_version,
                :status,
                :starts_at,
                :runtime_minutes,
                :turnaround_minutes,
                :ends_at,
                :room_available_at,
                :full_price_cents,
                :convenience_fee_cents
            )
        """, values)

    def move_session(self, session_id, new_start):
        self.connection.execute("""
            UPDATE sessions
            SET starts_at = ?,
                ends_at = ? + runtime_minutes * 60,
                room_available_at = ?
                    + runtime_minutes * 60
                    + turnaround_minutes * 60
            WHERE session_id = ?
        """, (new_start, new_start, new_start, session_id))

    def test_valid_session_is_accepted(self):
        self.insert_session()

        row = self.connection.execute("""
            SELECT starts_at, ends_at, room_available_at
            FROM sessions
            WHERE session_id = 'TEST-SESSION-001'
        """).fetchone()

        self.assertEqual(
            row,
            (BASE_START, BASE_START + 7200, BASE_START + 8400),
        )

    def test_unknown_catalog_references_are_rejected(self):
        cases = [
            {"movie_id": "UNKNOWN-MOVIE"},
            {"room_id": "UNKNOWN-ROOM"},
        ]

        for overrides in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.insert_session(**overrides)

    def test_unsupported_room_projection_is_rejected(self):
        # Room 005 supports only 2D.
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_session(
                room_id="CV-ROOM-005",
                projection_format="3D",
            )

    def test_invalid_audio_and_status_are_rejected(self):
        cases = [
            {"audio_version": "INVALID"},
            {"status": "INVALID"},
        ]

        for overrides in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.insert_session(**overrides)

    def test_invalid_timing_values_are_rejected(self):
        cases = [
            {"starts_at": 0},
            {"starts_at": BASE_START + 0.5},
            {"runtime_minutes": 0},
            {"runtime_minutes": -1},
            {"runtime_minutes": 1.5},
            {"turnaround_minutes": -1},
            {"turnaround_minutes": 0.5},
        ]

        for overrides in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.insert_session(**overrides)

    def test_inconsistent_end_time_is_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_session(ends_at=BASE_START + 60)

    def test_inconsistent_room_available_time_is_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_session(
                room_available_at=BASE_START + 7200
            )

    def test_negative_money_values_are_rejected(self):
        for field in ("full_price_cents", "convenience_fee_cents"):
            with self.subTest(field=field):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.insert_session(**{field: -1})

    def test_fractional_money_values_are_rejected(self):
        for field in ("full_price_cents", "convenience_fee_cents"):
            with self.subTest(field=field):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.insert_session(**{field: 100.5})

    def test_overlapping_session_is_rejected(self):
        self.insert_session()

        with self.assertRaisesRegex(
            sqlite3.IntegrityError,
            "overlaps",
        ):
            self.insert_session(
                session_id="TEST-SESSION-002",
                starts_at=BASE_START + 3600,
            )

    def test_turnaround_interval_blocks_next_session(self):
        self.insert_session()

        # Movie has ended, but the room is still in turnaround.
        with self.assertRaisesRegex(
            sqlite3.IntegrityError,
            "overlaps",
        ):
            self.insert_session(
                session_id="TEST-SESSION-002",
                starts_at=BASE_START + 7500,
            )

    def test_session_can_start_at_exact_available_time(self):
        self.insert_session()

        self.insert_session(
            session_id="TEST-SESSION-002",
            starts_at=BASE_START + 8400,
        )

        count = self.connection.execute(
            "SELECT COUNT(*) FROM sessions"
        ).fetchone()[0]

        self.assertEqual(count, 2)

    def test_different_rooms_can_share_start_time(self):
        self.insert_session()

        self.insert_session(
            session_id="TEST-SESSION-002",
            room_id="CV-ROOM-003",
        )

        count = self.connection.execute(
            "SELECT COUNT(*) FROM sessions"
        ).fetchone()[0]

        self.assertEqual(count, 2)

    def test_cancelled_session_does_not_block_room(self):
        self.insert_session(status="CANCELLED")

        self.insert_session(
            session_id="TEST-SESSION-002",
        )

        count = self.connection.execute(
            "SELECT COUNT(*) FROM sessions"
        ).fetchone()[0]

        self.assertEqual(count, 2)

    def test_rescheduling_into_conflict_is_rejected(self):
        self.insert_session()

        self.insert_session(
            session_id="TEST-SESSION-002",
            starts_at=BASE_START + 12000,
        )

        with self.assertRaisesRegex(
            sqlite3.IntegrityError,
            "overlaps",
        ):
            self.move_session(
                "TEST-SESSION-002",
                BASE_START + 60,
            )

        unchanged_start = self.connection.execute("""
            SELECT starts_at
            FROM sessions
            WHERE session_id = 'TEST-SESSION-002'
        """).fetchone()[0]

        self.assertEqual(unchanged_start, BASE_START + 12000)

    def test_reactivation_into_conflict_is_rejected(self):
        self.insert_session()

        self.insert_session(
            session_id="TEST-SESSION-002",
            status="CANCELLED",
        )

        with self.assertRaisesRegex(
            sqlite3.IntegrityError,
            "overlaps",
        ):
            self.connection.execute("""
                UPDATE sessions
                SET status = 'SCHEDULED'
                WHERE session_id = 'TEST-SESSION-002'
            """)

    def test_session_does_not_conflict_with_itself(self):
        self.insert_session()

        self.connection.execute("""
            UPDATE sessions
            SET starts_at = starts_at
            WHERE session_id = 'TEST-SESSION-001'
        """)

        count = self.connection.execute(
            "SELECT COUNT(*) FROM sessions"
        ).fetchone()[0]

        self.assertEqual(count, 1)

    def test_repeated_schema_preserves_sessions(self):
        self.insert_session()
        self.connection.commit()

        before = self.connection.execute(
            "SELECT * FROM sessions ORDER BY session_id"
        ).fetchall()

        self.connection.executescript(self.session_schema)

        after = self.connection.execute(
            "SELECT * FROM sessions ORDER BY session_id"
        ).fetchall()

        self.assertEqual(after, before)

    def test_foreign_keys_are_enabled_and_valid(self):
        self.insert_session()

        enabled = self.connection.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0]

        violations = self.connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        self.assertEqual(enabled, 1)
        self.assertEqual(violations, [])

    def test_duplicate_session_id_is_rejected(self):
        self.insert_session()

        # Different room avoids an overlap error masking the ID check.
        with self.assertRaisesRegex(
            sqlite3.IntegrityError,
            "UNIQUE",
        ):
            self.insert_session(room_id="CV-ROOM-003")


if __name__ == "__main__":
    unittest.main(verbosity=2)
