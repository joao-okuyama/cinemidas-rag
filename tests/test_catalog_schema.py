import sqlite3
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

SCHEMA_PATH = (
    PROJECT_ROOT
    / "src"
    / "booking"
    / "schema.sql"
)

FIXTURE_SQL = """
INSERT INTO cinemas (
    cinema_id, name, city, state, region
) VALUES (
    'TEST-CIN-001', 'Cinema de Teste', 'São Paulo', 'SP', 'Centro'
);

INSERT INTO rooms (
    room_id, cinema_id, name, category
) VALUES (
    'TEST-ROOM-001', 'TEST-CIN-001', 'Sala 1', 'STANDARD'
);

INSERT INTO room_formats (
    room_id, projection_format
) VALUES (
    'TEST-ROOM-001', '2D'
);

INSERT INTO seats (
    seat_id, room_id, row_label, seat_number
) VALUES (
    'TEST-SEAT-F6', 'TEST-ROOM-001', 'F', 6
);

INSERT INTO movies (
    movie_id, provider, provider_movie_id, title
) VALUES (
    'TEST-MOVIE-001', 'TEST_PROVIDER', '123', 'Filme de Teste'
);
"""


class CatalogSchemaTests(unittest.TestCase):
    """Valida as restrições do catálogo em uma base temporária."""

    @classmethod
    def setUpClass(cls):
        cls.schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

    def setUp(self):
        # Cada teste recebe uma base independente.
        self.connection = sqlite3.connect(":memory:")
        self.addCleanup(self.connection.close)

        self.connection.executescript(self.schema_sql)

        # A inicialização deve poder ser repetida.
        self.connection.executescript(self.schema_sql)

        foreign_keys_enabled = self.connection.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0]

        self.assertEqual(foreign_keys_enabled, 1)

        self.connection.executescript(FIXTURE_SQL)
        self.connection.commit()

    def assert_rejected(self, sql):
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(sql)

    def test_room_requires_existing_cinema(self):
        self.assert_rejected("""
            INSERT INTO rooms VALUES (
                'ROOM-X', 'CINEMA-INEXISTENTE', 'Sala X', 'STANDARD'
            )
        """)

    def test_room_name_is_unique_within_cinema(self):
        self.assert_rejected("""
            INSERT INTO rooms VALUES (
                'ROOM-X', 'TEST-CIN-001', 'Sala 1', 'VIP'
            )
        """)

    def test_invalid_room_category_is_rejected(self):
        self.assert_rejected("""
            INSERT INTO rooms VALUES (
                'ROOM-X', 'TEST-CIN-001', 'Sala X', 'INVALID'
            )
        """)

    def test_additional_valid_format_is_accepted(self):
        self.connection.execute("""
            INSERT INTO room_formats VALUES (
                'TEST-ROOM-001', '3D'
            )
        """)

        count = self.connection.execute("""
            SELECT COUNT(*)
            FROM room_formats
            WHERE room_id = 'TEST-ROOM-001'
        """).fetchone()[0]

        self.assertEqual(count, 2)

    def test_duplicate_room_format_is_rejected(self):
        self.assert_rejected("""
            INSERT INTO room_formats VALUES (
                'TEST-ROOM-001', '2D'
            )
        """)

    def test_unsupported_format_is_rejected(self):
        self.assert_rejected("""
            INSERT INTO room_formats VALUES (
                'TEST-ROOM-001', '4D'
            )
        """)

    def test_valid_seat_is_accepted(self):
        self.connection.execute("""
            INSERT INTO seats VALUES (
                'SEAT-X', 'TEST-ROOM-001', 'F', 7
            )
        """)

        seat = self.connection.execute("""
            SELECT row_label, seat_number
            FROM seats
            WHERE seat_id = 'SEAT-X'
        """).fetchone()

        self.assertEqual(seat, ("F", 7))

    def test_duplicate_seat_position_is_rejected(self):
        self.assert_rejected("""
            INSERT INTO seats VALUES (
                'SEAT-X', 'TEST-ROOM-001', 'F', 6
            )
        """)

    def test_invalid_seat_row_is_rejected(self):
        self.assert_rejected("""
            INSERT INTO seats VALUES (
                'SEAT-X', 'TEST-ROOM-001', 'K', 1
            )
        """)

    def test_invalid_seat_number_is_rejected(self):
        self.assert_rejected("""
            INSERT INTO seats VALUES (
                'SEAT-X', 'TEST-ROOM-001', 'A', 13
            )
        """)

    def test_incomplete_coordinates_are_rejected(self):
        self.assert_rejected("""
            UPDATE cinemas
            SET latitude = -23.55
            WHERE cinema_id = 'TEST-CIN-001'
        """)

    def test_unknown_movie_metadata_is_accepted(self):
        self.connection.execute("""
            INSERT INTO movies (movie_id, title)
            VALUES ('MOVIE-X', 'Filme sem metadados completos')
        """)

        metadata = self.connection.execute("""
            SELECT runtime_minutes, age_rating
            FROM movies
            WHERE movie_id = 'MOVIE-X'
        """).fetchone()

        self.assertEqual(metadata, (None, None))

    def test_duplicate_external_movie_id_is_rejected(self):
        self.assert_rejected("""
            INSERT INTO movies (
                movie_id, provider, provider_movie_id, title
            ) VALUES (
                'MOVIE-X', 'TEST_PROVIDER', '123', 'Outro título'
            )
        """)

    def test_negative_movie_runtime_is_rejected(self):
        self.assert_rejected("""
            INSERT INTO movies (
                movie_id, title, runtime_minutes
            ) VALUES (
                'MOVIE-X', 'Filme inválido', -10
            )
        """)

    def test_cinema_with_room_cannot_be_deleted(self):
        self.assert_rejected("""
            DELETE FROM cinemas
            WHERE cinema_id = 'TEST-CIN-001'
        """)


if __name__ == "__main__":
    unittest.main(verbosity=2)
