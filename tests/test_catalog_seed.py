import sqlite3
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BOOKING_DIRECTORY = PROJECT_ROOT / "src" / "booking"

EXPECTED_CINEMAS = [
    ("CV-CIN-001", "CineViva Centro", "Centro"),
    ("CV-CIN-002", "CineViva Sul", "Zona Sul"),
    ("CV-CIN-003", "CineViva Oeste", "Zona Oeste"),
]

EXPECTED_ROOMS = [
    ("CV-ROOM-001", "CV-CIN-001", "Sala 1", "STANDARD"),
    ("CV-ROOM-002", "CV-CIN-001", "Sala 2", "VIP"),
    ("CV-ROOM-003", "CV-CIN-002", "Sala 1", "STANDARD"),
    ("CV-ROOM-004", "CV-CIN-002", "Sala 2", "IMAX"),
    ("CV-ROOM-005", "CV-CIN-003", "Sala 1", "STANDARD"),
    ("CV-ROOM-006", "CV-CIN-003", "Sala 2", "VIP"),
]

EXPECTED_FORMATS = {
    ("CV-ROOM-001", "2D"),
    ("CV-ROOM-001", "3D"),
    ("CV-ROOM-002", "2D"),
    ("CV-ROOM-003", "2D"),
    ("CV-ROOM-003", "3D"),
    ("CV-ROOM-004", "2D"),
    ("CV-ROOM-004", "3D"),
    ("CV-ROOM-005", "2D"),
    ("CV-ROOM-006", "2D"),
    ("CV-ROOM-006", "3D"),
}


class CatalogSeedTests(unittest.TestCase):
    """Valida os dados iniciais em uma base independente."""

    @classmethod
    def setUpClass(cls):
        cls.schema_sql = (
            BOOKING_DIRECTORY / "schema.sql"
        ).read_text(encoding="utf-8")

        cls.seed_sql = (
            BOOKING_DIRECTORY / "seed_catalog.sql"
        ).read_text(encoding="utf-8")

    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.addCleanup(self.connection.close)

        self.connection.executescript(self.schema_sql)
        self.connection.executescript(self.seed_sql)

    def catalog_snapshot(self):
        # Os nomes das tabelas são constantes internas, não entradas do usuário.
        tables = (
            "cinemas",
            "rooms",
            "room_formats",
            "seats",
            "movies",
        )

        return {
            table: self.connection.execute(
                f"SELECT * FROM {table} ORDER BY 1, 2"
            ).fetchall()
            for table in tables
        }

    def test_expected_cinemas_are_created(self):
        rows = self.connection.execute("""
            SELECT cinema_id, name, region
            FROM cinemas
            ORDER BY cinema_id
        """).fetchall()

        self.assertEqual(rows, EXPECTED_CINEMAS)

        locations = self.connection.execute("""
            SELECT DISTINCT city, state, timezone, is_simulated
            FROM cinemas
        """).fetchall()

        self.assertEqual(
            locations,
            [("São Paulo", "SP", "America/Sao_Paulo", 1)],
        )

    def test_expected_rooms_are_created(self):
        rows = self.connection.execute("""
            SELECT room_id, cinema_id, name, category
            FROM rooms
            ORDER BY room_id
        """).fetchall()

        self.assertEqual(rows, EXPECTED_ROOMS)

    def test_expected_formats_are_created(self):
        rows = self.connection.execute("""
            SELECT room_id, projection_format
            FROM room_formats
        """).fetchall()

        self.assertEqual(set(rows), EXPECTED_FORMATS)
        self.assertEqual(len(rows), 10)

    def test_complete_seat_maps_are_created(self):
        expected_seats = {
            (
                f"{room_id}-{row_label}{seat_number:02d}",
                room_id,
                row_label,
                seat_number,
            )
            for room_id, _, _, _ in EXPECTED_ROOMS
            for row_label in "ABCDEFGHIJ"
            for seat_number in range(1, 13)
        }

        actual_seats = self.connection.execute("""
            SELECT seat_id, room_id, row_label, seat_number
            FROM seats
        """).fetchall()

        self.assertEqual(len(actual_seats), 720)
        self.assertEqual(set(actual_seats), expected_seats)

    def test_coordinates_remain_unknown(self):
        coordinates = self.connection.execute("""
            SELECT latitude, longitude
            FROM cinemas
        """).fetchall()

        self.assertEqual(coordinates, [(None, None)] * 3)

    def test_movies_are_not_seeded_yet(self):
        count = self.connection.execute(
            "SELECT COUNT(*) FROM movies"
        ).fetchone()[0]

        self.assertEqual(count, 0)

    def test_foreign_keys_are_valid(self):
        enabled = self.connection.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0]

        violations = self.connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        self.assertEqual(enabled, 1)
        self.assertEqual(violations, [])

    def test_repeated_seed_preserves_catalog(self):
        before = self.catalog_snapshot()

        self.connection.executescript(self.seed_sql)

        after = self.catalog_snapshot()

        self.assertEqual(after, before)

    def test_seed_does_not_overwrite_existing_values(self):
        self.connection.execute("""
            UPDATE cinemas
            SET name = 'Nome alterado para teste'
            WHERE cinema_id = 'CV-CIN-001'
        """)
        self.connection.commit()

        self.connection.executescript(self.seed_sql)

        name = self.connection.execute("""
            SELECT name
            FROM cinemas
            WHERE cinema_id = 'CV-CIN-001'
        """).fetchone()[0]

        self.assertEqual(name, "Nome alterado para teste")


if __name__ == "__main__":
    unittest.main(verbosity=2)
