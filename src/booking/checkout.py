"""Checkout e pagamentos estritamente simulados do CineViva."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .seat_holds import (
    _epoch,
    _required_identifier,
    _seat_labels,
    expire_holds,
)


PAYMENT_METHODS = {"PIX_MOCK", "CARD_MOCK", "LOYALTY_MOCK"}
TICKET_TYPES = {"FULL", "HALF"}


@dataclass(frozen=True)
class PaymentResult:
    payment_id: str
    order_id: str
    method: str
    status: str
    amount_cents: int
    mock_reference: str | None
    booking_code: str | None


def _ticket_selection(ticket_types: dict[str, str]) -> dict[str, str]:
    if not isinstance(ticket_types, dict) or not ticket_types:
        raise ValueError("Informe o tipo de ingresso de cada assento.")

    normalized = {}
    for raw_label, ticket_type in ticket_types.items():
        label = _seat_labels([raw_label])[0]
        if label in normalized:
            raise ValueError("A seleção contém assentos repetidos.")
        if ticket_type not in TICKET_TYPES:
            raise ValueError(
                "O tipo de ingresso deve ser FULL ou HALF."
            )
        normalized[label] = ticket_type

    return normalized


def get_order(
    connection: sqlite3.Connection,
    *,
    order_id: str,
    user_id: str,
) -> dict:
    order_id = _required_identifier(order_id, "order_id")
    user_id = _required_identifier(user_id, "user_id")

    row = connection.execute(
        "SELECT * FROM orders WHERE order_id = ? AND user_id = ?",
        (order_id, user_id),
    ).fetchone()

    if row is None:
        raise ValueError("Pedido não encontrado para este usuário.")

    order = dict(row)
    order["items"] = [
        dict(item)
        for item in connection.execute(
            """
            SELECT
                order_item_id, seat_id, seat_label, ticket_type,
                base_price_cents, discount_cents, fee_cents,
                total_cents, ticket_code
            FROM order_items
            WHERE order_id = ?
            ORDER BY seat_label
            """,
            (order_id,),
        )
    ]

    payment = connection.execute(
        """
        SELECT payment_id, method, status, amount_cents,
               mock_reference, created_at
        FROM payments
        WHERE order_id = ?
        ORDER BY created_at DESC, payment_id DESC
        LIMIT 1
        """,
        (order_id,),
    ).fetchone()
    order["latest_payment"] = dict(payment) if payment else None
    return order


def create_order(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    hold_id: str,
    ticket_types: dict[str, str],
    now: datetime | None = None,
) -> dict:
    """Cria um resumo imutável para todos os assentos da reserva."""
    if connection.in_transaction:
        raise RuntimeError(
            "Finalize a transação atual antes de criar o pedido."
        )

    user_id = _required_identifier(user_id, "user_id")
    hold_id = _required_identifier(hold_id, "hold_id")
    selection = _ticket_selection(ticket_types)
    now_epoch = _epoch(now)
    expire_holds(connection, now=now)
    order_id = f"CV-ORD-{uuid4().hex}"

    try:
        connection.execute("BEGIN IMMEDIATE")

        existing = connection.execute(
            """
            SELECT order_id
            FROM orders
            WHERE hold_id = ? AND user_id = ?
            """,
            (hold_id, user_id),
        ).fetchone()

        if existing is not None:
            saved_selection = {
                row["seat_label"]: row["ticket_type"]
                for row in connection.execute(
                    """
                    SELECT seat_label, ticket_type
                    FROM order_items
                    WHERE order_id = ?
                    """,
                    (existing["order_id"],),
                )
            }
            if saved_selection != selection:
                raise ValueError(
                    "O pedido já foi criado com outra seleção de ingressos."
                )
            order_id = existing["order_id"]
            connection.commit()
            return get_order(
                connection,
                order_id=order_id,
                user_id=user_id,
            )

        hold = connection.execute(
            """
            SELECT
                h.session_id,
                h.status AS hold_status,
                h.expires_at,
                s.full_price_cents,
                s.convenience_fee_cents,
                s.starts_at,
                s.projection_format,
                s.audio_version,
                m.title AS movie_title,
                c.name AS cinema_name,
                c.timezone AS cinema_timezone,
                r.name AS room_name
            FROM seat_holds AS h
            JOIN sessions AS s ON s.session_id = h.session_id
            JOIN movies AS m ON m.movie_id = s.movie_id
            JOIN rooms AS r ON r.room_id = s.room_id
            JOIN cinemas AS c ON c.cinema_id = r.cinema_id
            WHERE h.hold_id = ? AND h.user_id = ?
            """,
            (hold_id, user_id),
        ).fetchone()

        if hold is None:
            raise ValueError("Reserva não encontrada para este usuário.")
        if hold["hold_status"] != "ACTIVE" or hold["expires_at"] <= now_epoch:
            raise ValueError("A reserva não está mais ativa.")

        held_seats = connection.execute(
            """
            SELECT
                ss.seat_id,
                seat.row_label || seat.seat_number AS seat_label
            FROM session_seats AS ss
            JOIN seats AS seat ON seat.seat_id = ss.seat_id
            WHERE ss.hold_id = ? AND ss.status = 'HELD'
            ORDER BY seat.row_label, seat.seat_number
            """,
            (hold_id,),
        ).fetchall()
        by_label = {row["seat_label"]: row["seat_id"] for row in held_seats}

        if set(by_label) != set(selection):
            raise ValueError(
                "Informe o tipo de ingresso para todos os assentos reservados."
            )

        base_price = hold["full_price_cents"]
        fee_per_ticket = hold["convenience_fee_cents"]
        items = []

        for label in sorted(selection, key=lambda item: (item[0], int(item[1:]))):
            ticket_type = selection[label]
            discount = base_price // 2 if ticket_type == "HALF" else 0
            total = base_price - discount + fee_per_ticket
            items.append(
                (
                    f"CV-ITEM-{uuid4().hex}",
                    order_id,
                    by_label[label],
                    ticket_type,
                    base_price,
                    discount,
                    fee_per_ticket,
                    total,
                    label,
                )
            )

        subtotal = sum(item[4] for item in items)
        discount = sum(item[5] for item in items)
        fee = sum(item[6] for item in items)
        total = subtotal - discount + fee

        connection.execute(
            """
            INSERT INTO orders (
                order_id, user_id, session_id, hold_id, status,
                subtotal_cents, discount_cents, fee_cents, total_cents,
                created_at, movie_title, cinema_name, room_name,
                cinema_timezone, session_starts_at,
                projection_format, audio_version
            )
            VALUES (
                ?, ?, ?, ?, 'AWAITING_PAYMENT',
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                order_id,
                user_id,
                hold["session_id"],
                hold_id,
                subtotal,
                discount,
                fee,
                total,
                now_epoch,
                hold["movie_title"],
                hold["cinema_name"],
                hold["room_name"],
                hold["cinema_timezone"],
                hold["starts_at"],
                hold["projection_format"],
                hold["audio_version"],
            ),
        )
        connection.executemany(
            """
            INSERT INTO order_items (
                order_item_id, order_id, seat_id, ticket_type,
                base_price_cents, discount_cents, fee_cents,
                total_cents, seat_label
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            items,
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise

    return get_order(connection, order_id=order_id, user_id=user_id)


def pay_order(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    order_id: str,
    method: str,
    idempotency_key: str,
    now: datetime | None = None,
    succeed: bool = True,
) -> PaymentResult:
    """Executa uma tentativa fictícia; nunca recebe dados financeiros reais."""
    if connection.in_transaction:
        raise RuntimeError(
            "Finalize a transação atual antes de pagar o pedido."
        )

    user_id = _required_identifier(user_id, "user_id")
    order_id = _required_identifier(order_id, "order_id")
    idempotency_key = _required_identifier(
        idempotency_key, "idempotency_key"
    )
    if method not in PAYMENT_METHODS:
        raise ValueError("Método de pagamento simulado inválido.")
    if type(succeed) is not bool:
        raise ValueError("succeed deve ser booleano.")

    now_epoch = _epoch(now)
    expire_holds(connection, now=now)

    try:
        connection.execute("BEGIN IMMEDIATE")
        order = connection.execute(
            """
            SELECT o.*, h.status AS hold_status, h.expires_at
            FROM orders AS o
            JOIN seat_holds AS h ON h.hold_id = o.hold_id
            WHERE o.order_id = ? AND o.user_id = ?
            """,
            (order_id, user_id),
        ).fetchone()

        if order is None:
            raise ValueError("Pedido não encontrado para este usuário.")

        previous = connection.execute(
            """
            SELECT payment_id, order_id, method, status,
                   amount_cents, mock_reference
            FROM payments
            WHERE idempotency_key = ?
            """,
            (idempotency_key,),
        ).fetchone()

        if previous is not None:
            if (
                previous["order_id"] != order_id
                or previous["method"] != method
                or previous["amount_cents"] != order["total_cents"]
            ):
                raise ValueError(
                    "A chave de idempotência já pertence a outra operação."
                )
            connection.commit()
            return PaymentResult(
                payment_id=previous["payment_id"],
                order_id=order_id,
                method=method,
                status=previous["status"],
                amount_cents=previous["amount_cents"],
                mock_reference=previous["mock_reference"],
                booking_code=order["booking_code"],
            )

        if order["status"] != "AWAITING_PAYMENT":
            raise ValueError("O pedido não está aguardando pagamento.")
        if order["hold_status"] != "ACTIVE" or order["expires_at"] <= now_epoch:
            raise ValueError("A reserva expirou antes do pagamento.")

        payment_id = f"CV-PAY-{uuid4().hex}"
        payment_status = "SUCCEEDED" if succeed else "FAILED"
        reference = (
            f"{method}-SIM-{uuid4().hex[:12].upper()}"
            if succeed
            else None
        )

        connection.execute(
            """
            INSERT INTO payments (
                payment_id, order_id, method, status, amount_cents,
                idempotency_key, mock_reference, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payment_id,
                order_id,
                method,
                payment_status,
                order["total_cents"],
                idempotency_key,
                reference,
                now_epoch,
            ),
        )

        booking_code = None
        if succeed:
            booking_code = f"CV-{uuid4().hex[:10].upper()}"
            connection.execute(
                """
                UPDATE orders
                SET status = 'CONFIRMED', booking_code = ?, confirmed_at = ?
                WHERE order_id = ?
                """,
                (booking_code, now_epoch, order_id),
            )

            item_rows = connection.execute(
                """
                SELECT order_item_id
                FROM order_items
                WHERE order_id = ?
                """,
                (order_id,),
            ).fetchall()
            for item in item_rows:
                connection.execute(
                    """
                    UPDATE order_items
                    SET ticket_code = ?
                    WHERE order_item_id = ?
                    """,
                    (
                        f"CV-TKT-{uuid4().hex[:12].upper()}",
                        item["order_item_id"],
                    ),
                )

            updated_seats = connection.execute(
                """
                UPDATE session_seats
                SET status = 'BOOKED', hold_id = NULL, order_id = ?
                WHERE hold_id = ? AND status = 'HELD'
                """,
                (order_id, order["hold_id"]),
            ).rowcount

            if updated_seats != len(item_rows):
                raise RuntimeError(
                    "A quantidade de assentos do pedido ficou inconsistente."
                )

            connection.execute(
                """
                UPDATE seat_holds
                SET status = 'CONVERTED'
                WHERE hold_id = ? AND status = 'ACTIVE'
                """,
                (order["hold_id"],),
            )

        connection.commit()
    except Exception:
        connection.rollback()
        raise

    return PaymentResult(
        payment_id=payment_id,
        order_id=order_id,
        method=method,
        status=payment_status,
        amount_cents=order["total_cents"],
        mock_reference=reference,
        booking_code=booking_code,
    )


def list_user_orders(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    limit: int = 20,
) -> list[dict]:
    user_id = _required_identifier(user_id, "user_id")
    if type(limit) is not int or limit <= 0:
        raise ValueError("limit deve ser um inteiro positivo.")

    order_ids = [
        row["order_id"]
        for row in connection.execute(
            """
            SELECT order_id
            FROM orders
            WHERE user_id = ?
            ORDER BY created_at DESC, order_id DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
    ]
    return [
        get_order(connection, order_id=order_id, user_id=user_id)
        for order_id in order_ids
    ]


def render_voucher(order: dict) -> str:
    if not isinstance(order, dict) or order.get("status") != "CONFIRMED":
        raise ValueError("Somente pedidos confirmados possuem voucher.")

    try:
        cinema_timezone = ZoneInfo(order["cinema_timezone"])
    except (KeyError, ZoneInfoNotFoundError):
        raise ValueError("Fuso horário do pedido inválido.") from None

    session_time = datetime.fromtimestamp(
        order["session_starts_at"],
        tz=timezone.utc,
    ).astimezone(cinema_timezone)
    seats = ", ".join(item["seat_label"] for item in order["items"])
    ticket_codes = "\n".join(
        f"- {item['seat_label']}: {item['ticket_code']}"
        for item in order["items"]
    )

    return (
        "# CineViva — Ingresso simulado\n\n"
        "**SIMULAÇÃO — SEM VALIDADE**\n\n"
        f"Filme: {order['movie_title']}\n"
        f"Cinema: {order['cinema_name']}\n"
        f"Sala: {order['room_name']}\n"
        f"Sessão: {session_time:%d/%m/%Y às %H:%M}\n"
        f"Formato: {order['projection_format']} · {order['audio_version']}\n"
        f"Assentos: {seats}\n"
        f"Reserva: {order['booking_code']}\n\n"
        f"[QR CODE SIMULADO: {order['booking_code']}]\n\n"
        "Ingressos:\n"
        f"{ticket_codes}"
    )
