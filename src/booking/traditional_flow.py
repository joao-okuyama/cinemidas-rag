"""Fluxo determinístico compartilhado pela compra tradicional do site."""

from uuid import uuid4
import hashlib
import json

from .agent_tools import BookingAgentTools
from .checkout import get_order
from .seat_holds import _seat_labels, expire_holds
from .transactions import atomic


class TraditionalBookingFlow:
    """Orquestra a jornada por cliques sem depender do modelo de IA."""

    def __init__(self, tools: BookingAgentTools):
        self.tools = tools

    def choose_movie(self, movie_id: str) -> dict:
        movie = self.tools.select_movie(movie_id)
        return {"movie": movie, "sessions": self.tools.sessions(limit=100)}

    def choose_session(self, session_id: str) -> dict:
        session = self.tools.select_session(session_id)
        seat_map = self.tools.seat_map()
        return {
            "session": session,
            "seat_map": seat_map["text"],
            "available_seats": [
                seat["label"]
                for seat in seat_map["seats"]
                if seat["status"] == "AVAILABLE"
            ],
        }

    def hold(self, seat_labels: list[str]) -> dict:
        if not seat_labels:
            raise ValueError("Selecione pelo menos um assento.")
        return self.tools.hold_seats(seat_labels)

    def checkout(
        self,
        seat_labels: list[str],
        half_price_seats: list[str] | None = None,
    ) -> dict:
        if not seat_labels:
            raise ValueError("Selecione e reserve os assentos primeiro.")

        half_price = set(half_price_seats or [])
        if not half_price.issubset(set(seat_labels)):
            raise ValueError(
                "A meia-entrada deve corresponder a um assento selecionado."
            )

        return self.tools.checkout(
            {
                label: "HALF" if label in half_price else "FULL"
                for label in seat_labels
            }
        )

    def continue_to_checkout(
        self,
        seat_labels: list[str],
        half_price_seats: list[str] | None = None,
        *,
        request_id: str | None = None,
        movie_id: str | None = None,
        session_id: str | None = None,
        now=None,
    ) -> dict:
        """One atomic operation; a retry never releases/recreates its hold."""
        labels = _seat_labels(seat_labels)
        if len(labels) > 12:
            raise ValueError("Selecione no máximo 12 assentos por pedido.")
        halves = set(_seat_labels(half_price_seats) if half_price_seats else [])
        if not halves.issubset(labels):
            raise ValueError("A meia-entrada deve corresponder a um assento selecionado.")
        current = self.tools.state()
        movie_id = movie_id or current["selected_movie_id"]
        session_id = session_id or current["selected_session_id"]
        selection = {label: "HALF" if label in halves else "FULL" for label in labels}
        fingerprint = hashlib.sha256(json.dumps(
            [movie_id, session_id, selection], sort_keys=True
        ).encode()).hexdigest()
        request_id = request_id or f"FLOW-{uuid4().hex}"
        connection = self.tools.connection
        expire_holds(connection, now=now)
        with atomic(connection):
            previous = connection.execute(
                "SELECT * FROM checkout_requests WHERE user_id=? AND request_id=?",
                (self.tools.user_id, request_id),
            ).fetchone()
            if previous:
                if previous["selection_hash"] != fingerprint:
                    raise ValueError("Esta tentativa já pertence a outra seleção.")
                order = get_order(connection, order_id=previous["order_id"], user_id=self.tools.user_id)
                hold = dict(connection.execute(
                    "SELECT hold_id, expires_at FROM seat_holds WHERE hold_id=?", (order["hold_id"],)
                ).fetchone())
                return {"hold": hold, "order": order}
            if movie_id != current["selected_movie_id"]:
                self.tools.select_movie(movie_id, now=now)
            if session_id != self.tools.state()["selected_session_id"]:
                self.tools.select_session(session_id, now=now)
            hold = self.tools.hold_seats(list(labels), now=now)
            order = self.tools.checkout(selection, now=now)
            connection.execute(
                "INSERT INTO checkout_requests VALUES (?, ?, ?, ?)",
                (self.tools.user_id, request_id, fingerprint, order["order_id"]),
            )
            return {"hold": hold, "order": order}

    def pay(self, method: str) -> dict:
        payment = self.tools.pay(
            method,
            idempotency_key=f"SITE-{uuid4().hex}",
        )
        return {"payment": payment, "voucher": self.tools.voucher()}
