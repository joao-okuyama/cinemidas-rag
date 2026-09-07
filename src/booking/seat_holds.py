"""Disponibilidade e reservas temporárias de assentos."""

import re
import sqlite3

from .transactions import atomic
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4


class SeatUnavailableError(RuntimeError):
    def __init__(self, labels: list[str]):
        self.labels = tuple(labels)
        super().__init__(
            "Assentos indisponíveis: " + ", ".join(self.labels)
        )


@dataclass(frozen=True)
class SeatHoldResult:
    hold_id: str
    user_id: str
    session_id: str
    seat_labels: tuple[str, ...]
    created_at: int
    expires_at: int


def _epoch(now: datetime | None) -> int:
    if now is None:
        now = datetime.now(timezone.utc)

    if (
        not isinstance(now, datetime)
        or now.tzinfo is None
        or now.utcoffset() is None
    ):
        raise ValueError("now deve ser um datetime com fuso horário.")

    value = int(now.astimezone(timezone.utc).timestamp())
    if value <= 0:
        raise ValueError("now deve representar um instante positivo.")
    return value


def _required_identifier(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} deve ser um texto preenchido.")
    return value.strip()


def _seat_labels(values: list[str]) -> tuple[str, ...]:
    if not isinstance(values, list) or not values:
        raise ValueError("Informe ao menos um assento.")
    if len(values) > 12:
        raise ValueError("Selecione no máximo 12 assentos por pedido.")

    labels = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError("Cada assento deve ser informado como texto.")

        label = value.strip().upper()
        match = re.fullmatch(r"([A-J])(0?[1-9]|1[0-2])", label)
        if match is None:
            raise ValueError(f"Assento inválido: {value!r}.")
        labels.append(f"{match.group(1)}{int(match.group(2))}")

    if len(set(labels)) != len(labels):
        raise ValueError("A solicitação contém assentos repetidos.")

    return tuple(
        sorted(labels, key=lambda label: (label[0], int(label[1:])))
    )


def _initialize_session_seats(
    connection: sqlite3.Connection,
    session_id: str,
) -> None:
    connection.execute(
        """
        INSERT INTO session_seats (session_id, seat_id, status)
        SELECT s.session_id, seat.seat_id, 'AVAILABLE'
        FROM sessions AS s
        JOIN seats AS seat ON seat.room_id = s.room_id
        WHERE s.session_id = ?
        ON CONFLICT (session_id, seat_id) DO NOTHING
        """,
        (session_id,),
    )


def _expire_holds_in_transaction(
    connection: sqlite3.Connection,
    now_epoch: int,
) -> int:
    expired_ids = [
        row["hold_id"]
        for row in connection.execute(
            """
            SELECT hold_id
            FROM seat_holds
            WHERE status = 'ACTIVE' AND expires_at <= ?
            """,
            (now_epoch,),
        )
    ]

    if not expired_ids:
        return 0

    placeholders = ",".join("?" for _ in expired_ids)
    connection.execute(
        f"""
        UPDATE session_seats
        SET status = 'AVAILABLE', hold_id = NULL, order_id = NULL
        WHERE status = 'HELD' AND hold_id IN ({placeholders})
        """,
        expired_ids,
    )
    connection.execute(
        f"""
        UPDATE seat_holds
        SET status = 'EXPIRED'
        WHERE status = 'ACTIVE' AND hold_id IN ({placeholders})
        """,
        expired_ids,
    )
    connection.execute(
        f"""
        UPDATE orders
        SET status = 'EXPIRED'
        WHERE status IN ('DRAFT', 'AWAITING_PAYMENT')
          AND hold_id IN ({placeholders})
        """,
        expired_ids,
    )
    return len(expired_ids)


def expire_holds(
    connection: sqlite3.Connection,
    *,
    now: datetime | None = None,
) -> int:
    now_epoch = _epoch(now)
    with atomic(connection):
        expired = _expire_holds_in_transaction(connection, now_epoch)
        return expired


def create_seat_hold(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    session_id: str,
    seat_labels: list[str],
    now: datetime | None = None,
    hold_seconds: int = 300,
) -> SeatHoldResult:
    """Reserva o grupo completo por cinco minutos ou não reserva nenhum."""
    user_id = _required_identifier(user_id, "user_id")
    session_id = _required_identifier(session_id, "session_id")
    labels = _seat_labels(seat_labels)
    now_epoch = _epoch(now)

    if type(hold_seconds) is not int or hold_seconds <= 0:
        raise ValueError("hold_seconds deve ser um inteiro positivo.")

    expire_holds(connection, now=now)

    hold_id = f"CV-HOLD-{uuid4().hex}"
    expires_at = now_epoch + hold_seconds

    with atomic(connection):

        session = connection.execute(
            """
            SELECT session_id, room_id, starts_at, status
            FROM sessions
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()

        if session is None:
            raise ValueError("A sessão informada não existe.")
        if session["status"] != "SCHEDULED":
            raise ValueError("A sessão não está disponível para reserva.")
        if session["starts_at"] <= now_epoch:
            raise ValueError("A sessão já começou.")

        connection.execute(
            """
            INSERT INTO users (user_id, created_at)
            VALUES (?, ?)
            ON CONFLICT (user_id) DO NOTHING
            """,
            (user_id, now_epoch),
        )
        _initialize_session_seats(connection, session_id)

        placeholders = ",".join("?" for _ in labels)
        rows = connection.execute(
            f"""
            SELECT
                seat.seat_id,
                seat.row_label || seat.seat_number AS seat_label,
                ss.status
            FROM seats AS seat
            JOIN session_seats AS ss
              ON ss.seat_id = seat.seat_id
             AND ss.session_id = ?
            WHERE seat.row_label || seat.seat_number
                  IN ({placeholders})
            """,
            (session_id, *labels),
        ).fetchall()

        by_label = {row["seat_label"]: row for row in rows}
        missing = [label for label in labels if label not in by_label]
        if missing:
            raise ValueError(
                "Assentos inexistentes para esta sessão: "
                + ", ".join(missing)
            )

        unavailable = [
            label
            for label in labels
            if by_label[label]["status"] != "AVAILABLE"
        ]
        if unavailable:
            raise SeatUnavailableError(unavailable)

        connection.execute(
            """
            INSERT INTO seat_holds (
                hold_id, user_id, session_id,
                status, created_at, expires_at
            )
            VALUES (?, ?, ?, 'ACTIVE', ?, ?)
            """,
            (hold_id, user_id, session_id, now_epoch, expires_at),
        )

        for label in labels:
            updated = connection.execute(
                """
                UPDATE session_seats
                SET status = 'HELD', hold_id = ?, order_id = NULL
                WHERE session_id = ?
                  AND seat_id = ?
                  AND status = 'AVAILABLE'
                """,
                (hold_id, session_id, by_label[label]["seat_id"]),
            ).rowcount

            if updated != 1:
                raise SeatUnavailableError([label])


    return SeatHoldResult(
        hold_id=hold_id,
        user_id=user_id,
        session_id=session_id,
        seat_labels=labels,
        created_at=now_epoch,
        expires_at=expires_at,
    )


def release_hold(
    connection: sqlite3.Connection,
    *,
    hold_id: str,
    user_id: str,
    now: datetime | None = None,
) -> bool:
    hold_id = _required_identifier(hold_id, "hold_id")
    user_id = _required_identifier(user_id, "user_id")
    expire_holds(connection, now=now)

    with atomic(connection):
        hold = connection.execute(
            """
            SELECT status
            FROM seat_holds
            WHERE hold_id = ? AND user_id = ?
            """,
            (hold_id, user_id),
        ).fetchone()

        if hold is None:
            raise ValueError("Reserva não encontrada para este usuário.")
        if hold["status"] != "ACTIVE":
            return False

        connection.execute(
            """
            UPDATE session_seats
            SET status = 'AVAILABLE', hold_id = NULL, order_id = NULL
            WHERE hold_id = ? AND status = 'HELD'
            """,
            (hold_id,),
        )
        connection.execute(
            "UPDATE seat_holds SET status = 'RELEASED' WHERE hold_id = ?",
            (hold_id,),
        )
        connection.execute(
            """
            UPDATE orders
            SET status = 'CANCELLED'
            WHERE hold_id = ?
              AND status IN ('DRAFT', 'AWAITING_PAYMENT')
            """,
            (hold_id,),
        )
        return True


def get_seat_map(
    connection: sqlite3.Connection,
    *,
    session_id: str,
    user_id: str | None = None,
    now: datetime | None = None,
) -> list[dict]:
    session_id = _required_identifier(session_id, "session_id")
    if user_id is not None:
        user_id = _required_identifier(user_id, "user_id")

    expire_holds(connection, now=now)

    with atomic(connection):
        exists = connection.execute(
            "SELECT 1 FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if exists is None:
            raise ValueError("A sessão informada não existe.")

        _initialize_session_seats(connection, session_id)
        rows = connection.execute(
            """
            SELECT
                seat.row_label,
                seat.seat_number,
                ss.status,
                hold.user_id AS holding_user
            FROM session_seats AS ss
            JOIN seats AS seat ON seat.seat_id = ss.seat_id
            LEFT JOIN seat_holds AS hold ON hold.hold_id = ss.hold_id
            WHERE ss.session_id = ?
            ORDER BY seat.row_label, seat.seat_number
            """,
            (session_id,),
        ).fetchall()

    result = []
    for row in rows:
        if row["status"] == "AVAILABLE":
            display_status = "AVAILABLE"
        elif (
            row["status"] == "HELD"
            and user_id is not None
            and row["holding_user"] == user_id
        ):
            display_status = "SELECTED"
        else:
            display_status = "OCCUPIED"

        result.append(
            {
                "label": f"{row['row_label']}{row['seat_number']}",
                "row": row["row_label"],
                "number": row["seat_number"],
                "status": display_status,
            }
        )

    return result


def render_text_seat_map(seats: list[dict]) -> str:
    symbols = {
        "AVAILABLE": "□",
        "OCCUPIED": "■",
        "SELECTED": "●",
    }
    rows = {}
    for seat in seats:
        rows.setdefault(seat["row"], []).append(seat)

    lines = ["TELA", ""]
    for row_label in sorted(rows):
        cells = " ".join(
            f"{symbols[seat['status']]}{seat['number']:02d}"
            for seat in rows[row_label]
        )
        lines.append(f"{row_label}  {cells}")

    lines.extend(
        ["", "□ Disponível  ■ Ocupado  ● Selecionado"]
    )
    return "\n".join(lines)
