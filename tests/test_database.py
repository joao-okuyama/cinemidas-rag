import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.booking.database import (
    connect_database,
    initialize_database,
)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory(
            prefix="cinemidas-database-tests-"
        )
        self.addCleanup(temporary_directory.cleanup)

        self.database_path = (
            Path(temporary_directory.name) / "cinemidas-test.db"
        )

        self.connection = self.open_connection()

    def open_connection(self):
        connection = connect_database(self.database_path)
        self.addCleanup(connection.close)
        return connection

    def test_foreign_keys_are_enabled(self):
        enabled = self.connection.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0]

        self.assertEqual(enabled, 1)

    def test_rows_support_column_names(self):
        row = self.connection.execute(
            "SELECT 42 AS expected_value"
        ).fetchone()

        self.assertIsInstance(row, sqlite3.Row)
        self.assertEqual(row["expected_value"], 42)

    def test_initialization_creates_tables_without_seed(self):
        initialize_database(self.connection)

        tables = {
            row["name"]
            for row in self.connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            )
        }

        expected_tables = {
            "cinemas",
            "rooms",
            "room_formats",
            "seats",
            "movies",
            "sessions",
        }

        self.assertTrue(expected_tables.issubset(tables))

        for table in sorted(expected_tables):
            with self.subTest(table=table):
                # Os nomes vêm exclusivamente da lista fixa acima.
                count = self.connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]

                self.assertEqual(count, 0)

    def test_initialization_can_seed_catalog(self):
        initialize_database(
            self.connection,
            seed_catalog=True,
        )

        expected_counts = {
            "cinemas": 3,
            "rooms": 6,
            "room_formats": 10,
            "seats": 720,
            "movies": 0,
            "sessions": 0,
        }

        for table, expected_count in expected_counts.items():
            with self.subTest(table=table):
                # Os nomes vêm exclusivamente do dicionário fixo acima.
                actual_count = self.connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]

                self.assertEqual(actual_count, expected_count)

    def test_repeated_initialization_preserves_existing_values(self):
        initialize_database(
            self.connection,
            seed_catalog=True,
        )

        self.connection.execute(
            """
            UPDATE cinemas
            SET name = ?
            WHERE cinema_id = ?
            """,
            ("Nome preservado", "CV-CIN-001"),
        )
        self.connection.commit()

        initialize_database(
            self.connection,
            seed_catalog=True,
        )

        name = self.connection.execute(
            """
            SELECT name
            FROM cinemas
            WHERE cinema_id = ?
            """,
            ("CV-CIN-001",),
        ).fetchone()["name"]

        seat_count = self.connection.execute(
            "SELECT COUNT(*) FROM seats"
        ).fetchone()[0]

        self.assertEqual(name, "Nome preservado")
        self.assertEqual(seat_count, 720)

    def test_committed_data_survives_reopening_database(self):
        initialize_database(
            self.connection,
            seed_catalog=True,
        )

        self.connection.execute(
            """
            UPDATE cinemas
            SET name = ?
            WHERE cinema_id = ?
            """,
            ("Nome persistido", "CV-CIN-001"),
        )
        self.connection.commit()
        self.connection.close()

        reopened_connection = self.open_connection()

        name = reopened_connection.execute(
            """
            SELECT name
            FROM cinemas
            WHERE cinema_id = ?
            """,
            ("CV-CIN-001",),
        ).fetchone()["name"]

        self.assertTrue(self.database_path.is_file())
        self.assertEqual(name, "Nome persistido")

    def test_every_connection_enables_foreign_keys(self):
        second_connection = self.open_connection()

        for connection in (
            self.connection,
            second_connection,
        ):
            enabled = connection.execute(
                "PRAGMA foreign_keys"
            ).fetchone()[0]

            self.assertEqual(enabled, 1)

    def test_initialization_rejects_active_transaction(self):
        self.connection.execute("BEGIN")

        with self.assertRaisesRegex(
            RuntimeError,
            "transação atual",
        ):
            initialize_database(self.connection)

        # A função não deve confirmar nem desfazer a transação do chamador.
        self.assertTrue(self.connection.in_transaction)
        self.connection.rollback()

    def test_connection_rejects_invalid_foreign_key(self):
        initialize_database(self.connection)

        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO rooms (
                    room_id,
                    cinema_id,
                    name,
                    category
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    "TEST-ROOM",
                    "NONEXISTENT-CINEMA",
                    "Sala de teste",
                    "STANDARD",
                ),
            )

        self.connection.rollback()

    def test_busy_timeout_is_five_seconds(self):
        timeout_milliseconds = self.connection.execute(
            "PRAGMA busy_timeout"
        ).fetchone()[0]

        self.assertEqual(timeout_milliseconds, 5000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
