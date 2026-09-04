import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.booking.database import (
    connect_database,
    initialize_database,
)
from src.booking.migrations import apply_migrations


class MigrationTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory(
            prefix="cinemidas-migration-tests-"
        )
        self.addCleanup(temporary_directory.cleanup)

        self.directory = Path(temporary_directory.name)

        self.connection = connect_database(":memory:")
        self.addCleanup(self.connection.close)

        initialize_database(self.connection, migrate=False)

    def write_migration(self, name, content):
        path = self.directory / name
        path.write_text(content, encoding="utf-8")
        return path

    def apply_test_migrations(self):
        return apply_migrations(
            self.connection,
            migrations_directory=self.directory,
        )

    def table_exists(self, name):
        return self.connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (name,),
        ).fetchone() is not None

    def test_real_migration_preserves_movies_and_adds_presentation(self):
        self.connection.execute(
            """
            INSERT INTO movies (movie_id, title)
            VALUES (?, ?)
            """,
            ("TEST-MOVIE", "Filme preservado"),
        )
        self.connection.commit()

        applied = apply_migrations(self.connection)

        self.assertEqual(
            applied,
            [
                "001_movie_presentation.sql",
                "002_catalog_collections.sql",
            ],
        )

        movie = self.connection.execute(
            """
            SELECT title, poster_path
            FROM movies
            WHERE movie_id = ?
            """,
            ("TEST-MOVIE",),
        ).fetchone()

        self.assertEqual(movie["title"], "Filme preservado")
        self.assertIsNone(movie["poster_path"])
        self.assertTrue(self.table_exists("genres"))
        self.assertTrue(self.table_exists("movie_genres"))

        self.connection.execute(
            """
            UPDATE movies
            SET poster_path = ?
            WHERE movie_id = ?
            """,
            ("/poster-teste.jpg", "TEST-MOVIE"),
        )
        self.connection.execute(
            "INSERT INTO genres (genre_id, name) VALUES (?, ?)",
            (28, "Ação"),
        )
        self.connection.execute(
            """
            INSERT INTO movie_genres (movie_id, genre_id)
            VALUES (?, ?)
            """,
            ("TEST-MOVIE", 28),
        )
        self.connection.commit()

        genre = self.connection.execute(
            """
            SELECT g.name
            FROM genres AS g
            JOIN movie_genres AS mg
                ON mg.genre_id = g.genre_id
            WHERE mg.movie_id = ?
            """,
            ("TEST-MOVIE",),
        ).fetchone()

        self.assertEqual(genre["name"], "Ação")
        self.assertEqual(
            self.connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall(),
            [],
        )

    def test_repeated_execution_does_not_reapply_migration(self):
        self.write_migration(
            "001_example.sql",
            "CREATE TABLE example (id INTEGER PRIMARY KEY);",
        )

        self.assertEqual(
            self.apply_test_migrations(),
            ["001_example.sql"],
        )

        before = [
            tuple(row)
            for row in self.connection.execute(
                "SELECT * FROM schema_migrations"
            )
        ]

        self.assertEqual(self.apply_test_migrations(), [])

        after = [
            tuple(row)
            for row in self.connection.execute(
                "SELECT * FROM schema_migrations"
            )
        ]

        self.assertEqual(after, before)

    def test_changed_applied_migration_is_rejected(self):
        self.write_migration(
            "001_example.sql",
            "CREATE TABLE example (id INTEGER);",
        )
        self.apply_test_migrations()

        self.write_migration(
            "001_example.sql",
            "CREATE TABLE example (id INTEGER, name TEXT);",
        )

        with self.assertRaisesRegex(RuntimeError, "alterada"):
            self.apply_test_migrations()

        columns = [
            row["name"]
            for row in self.connection.execute(
                "PRAGMA table_info(example)"
            )
        ]

        self.assertEqual(columns, ["id"])
        self.assertFalse(self.connection.in_transaction)

    def test_missing_applied_migration_is_rejected(self):
        path = self.write_migration(
            "001_example.sql",
            "CREATE TABLE example (id INTEGER);",
        )
        self.apply_test_migrations()

        # Remove apenas um arquivo criado neste diretório temporário.
        path.unlink()

        with self.assertRaisesRegex(RuntimeError, "ausente"):
            self.apply_test_migrations()

        self.assertTrue(self.table_exists("example"))

    def test_failure_rolls_back_all_pending_schema_and_data_changes(self):
        self.connection.execute(
            """
            INSERT INTO movies (movie_id, title)
            VALUES ('TEST-MOVIE', 'Título original')
            """
        )
        self.connection.commit()

        self.write_migration(
            "001_first.sql",
            """
            CREATE TABLE temporary_feature (id INTEGER);
            UPDATE movies SET title = 'Título alterado';
            """,
        )
        self.write_migration(
            "002_broken.sql",
            "INSERT INTO nonexistent_table VALUES (1);",
        )

        with self.assertRaises(sqlite3.Error):
            self.apply_test_migrations()

        self.assertFalse(self.table_exists("temporary_feature"))
        self.assertFalse(self.table_exists("schema_migrations"))

        title = self.connection.execute(
            "SELECT title FROM movies WHERE movie_id = 'TEST-MOVIE'"
        ).fetchone()["title"]

        self.assertEqual(title, "Título original")
        self.assertFalse(self.connection.in_transaction)

    def test_foreign_key_violation_rolls_back_migration(self):
        self.write_migration(
            "001_invalid_reference.sql",
            """
            PRAGMA defer_foreign_keys = ON;

            INSERT INTO rooms (
                room_id, cinema_id, name, category
            )
            VALUES (
                'TEST-ROOM',
                'NONEXISTENT-CINEMA',
                'Sala de teste',
                'STANDARD'
            );
            """,
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "referências inválidas",
        ):
            self.apply_test_migrations()

        room_count = self.connection.execute(
            "SELECT COUNT(*) FROM rooms"
        ).fetchone()[0]

        self.assertEqual(room_count, 0)
        self.assertFalse(self.table_exists("schema_migrations"))
        self.assertFalse(self.connection.in_transaction)

    def test_active_transaction_is_rejected_and_preserved(self):
        self.connection.execute("BEGIN")

        with self.assertRaisesRegex(
            RuntimeError,
            "transação atual",
        ):
            self.apply_test_migrations()

        self.assertTrue(self.connection.in_transaction)
        self.assertFalse(self.table_exists("schema_migrations"))

        self.connection.rollback()

    def test_disabled_foreign_keys_are_rejected(self):
        self.connection.execute("PRAGMA foreign_keys = OFF")

        with self.assertRaisesRegex(
            RuntimeError,
            "integridade referencial",
        ):
            self.apply_test_migrations()

        self.assertFalse(self.table_exists("schema_migrations"))

    def test_duplicate_versions_are_rejected(self):
        self.write_migration(
            "001_first.sql",
            "CREATE TABLE first_table (id INTEGER);",
        )
        self.write_migration(
            "001_second.sql",
            "CREATE TABLE second_table (id INTEGER);",
        )

        with self.assertRaisesRegex(
            ValueError,
            "Versão de migração duplicada",
        ):
            self.apply_test_migrations()

        self.assertFalse(self.table_exists("first_table"))
        self.assertFalse(self.table_exists("second_table"))
        self.assertFalse(self.table_exists("schema_migrations"))

    def test_older_pending_migration_is_rejected(self):
        self.write_migration(
            "002_second.sql",
            "CREATE TABLE second_table (id INTEGER);",
        )
        self.apply_test_migrations()

        self.write_migration(
            "001_first.sql",
            "CREATE TABLE first_table (id INTEGER);",
        )

        with self.assertRaisesRegex(RuntimeError, "anterior"):
            self.apply_test_migrations()

        self.assertFalse(self.table_exists("first_table"))
        self.assertTrue(self.table_exists("second_table"))

    def test_semicolons_inside_text_are_preserved(self):
        self.write_migration(
            "001_text.sql",
            """
            CREATE TABLE notes (message TEXT);
            INSERT INTO notes VALUES ('Ação; aventura');
            -- Comentário final.
            """,
        )

        self.apply_test_migrations()

        message = self.connection.execute(
            "SELECT message FROM notes"
        ).fetchone()["message"]

        self.assertEqual(message, "Ação; aventura")

    def test_trigger_with_multiple_statements_is_supported(self):
        self.write_migration(
            "001_trigger.sql",
            """
            CREATE TABLE events (id INTEGER);
            CREATE TABLE audit (message TEXT);

            CREATE TRIGGER record_event
            AFTER INSERT ON events
            BEGIN
                INSERT INTO audit VALUES ('primeiro');
                INSERT INTO audit VALUES ('segundo');
            END;

            INSERT INTO events VALUES (1);
            """,
        )

        self.apply_test_migrations()

        messages = [
            row["message"]
            for row in self.connection.execute(
                "SELECT message FROM audit ORDER BY rowid"
            )
        ]

        self.assertEqual(messages, ["primeiro", "segundo"])

    def test_missing_directory_is_rejected(self):
        with self.assertRaises(FileNotFoundError):
            apply_migrations(
                self.connection,
                migrations_directory=self.directory / "missing",
            )

        self.assertFalse(self.table_exists("schema_migrations"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
