"""Fachada determinística das ações disponíveis ao agente conversacional."""

import sqlite3
from datetime import datetime, timezone

from .checkout import (
    create_order,
    get_order,
    list_user_orders,
    pay_order,
    render_voucher,
)
from .public_catalog import list_public_catalog
from .seat_holds import (
    _epoch,
    _required_identifier,
    create_seat_hold,
    get_seat_map,
    release_hold,
    render_text_seat_map,
)
from .session_scheduler import list_session_options


class BookingAgentTools:
    """Executa ações; o modelo apenas escolhe qual método chamar."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: str,
        conversation_id: str,
        channel: str = "WEB",
        now: datetime | None = None,
    ):
        self.connection = connection
        self.user_id = _required_identifier(user_id, "user_id")
        self.conversation_id = _required_identifier(
            conversation_id, "conversation_id"
        )

        if channel not in {"WEB", "WHATSAPP", "TELEGRAM"}:
            raise ValueError("Canal de conversa inválido.")

        self.channel = channel
        self._ensure_conversation(now=now)

    def _ensure_conversation(self, *, now: datetime | None) -> None:
        now_epoch = _epoch(now)

        try:
            self.connection.execute("BEGIN IMMEDIATE")
            self.connection.execute(
                """
                INSERT INTO users (user_id, created_at)
                VALUES (?, ?)
                ON CONFLICT (user_id) DO NOTHING
                """,
                (self.user_id, now_epoch),
            )

            existing = self.connection.execute(
                """
                SELECT user_id
                FROM conversation_sessions
                WHERE conversation_id = ?
                """,
                (self.conversation_id,),
            ).fetchone()

            if existing is not None and existing["user_id"] != self.user_id:
                raise ValueError(
                    "A conversa não pertence ao usuário autenticado."
                )

            self.connection.execute(
                """
                INSERT INTO conversation_sessions (
                    conversation_id, user_id, channel, state, updated_at
                )
                VALUES (?, ?, ?, 'DISCOVERY', ?)
                ON CONFLICT (conversation_id) DO NOTHING
                """,
                (
                    self.conversation_id,
                    self.user_id,
                    self.channel,
                    now_epoch,
                ),
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def state(self) -> dict:
        row = self.connection.execute(
            """
            SELECT *
            FROM conversation_sessions
            WHERE conversation_id = ? AND user_id = ?
            """,
            (self.conversation_id, self.user_id),
        ).fetchone()

        if row is None:
            raise RuntimeError("Estado da conversa não encontrado.")
        return dict(row)

    def _update_state(
        self,
        state: str,
        *,
        now: datetime | None,
        selected_movie_id=None,
        selected_cinema_id=None,
        selected_session_id=None,
        active_hold_id=None,
        active_order_id=None,
    ) -> dict:
        now_epoch = _epoch(now)
        self.connection.execute(
            """
            UPDATE conversation_sessions
            SET state = ?,
                selected_movie_id = ?,
                selected_cinema_id = ?,
                selected_session_id = ?,
                active_hold_id = ?,
                active_order_id = ?,
                updated_at = ?
            WHERE conversation_id = ? AND user_id = ?
            """,
            (
                state,
                selected_movie_id,
                selected_cinema_id,
                selected_session_id,
                active_hold_id,
                active_order_id,
                now_epoch,
                self.conversation_id,
                self.user_id,
            ),
        )
        self.connection.commit()
        return self.state()

    def catalog(
        self,
        *,
        query: str | None = None,
        genre: str | None = None,
        limit: int = 5,
        now: datetime | None = None,
    ) -> list[dict]:
        if query is not None and not isinstance(query, str):
            raise ValueError("query deve ser texto ou nulo.")
        if genre is not None and not isinstance(genre, str):
            raise ValueError("genre deve ser texto ou nulo.")

        candidates = list_public_catalog(
            self.connection,
            now=now,
            limit=500,
            only_bookable=False,
        )
        query_key = query.strip().casefold() if query else None
        genre_key = genre.strip().casefold() if genre else None

        if query_key:
            candidates = [
                movie
                for movie in candidates
                if query_key in movie["title"].casefold()
                or query_key in movie["synopsis"].casefold()
            ]

        if genre_key:
            candidates = [
                movie
                for movie in candidates
                if any(
                    genre_key == name.casefold()
                    for name in movie["genres"]
                )
            ]

        if type(limit) is not int or limit <= 0:
            raise ValueError("limit deve ser um inteiro positivo.")
        return candidates[:limit]

    def select_movie(
        self,
        movie_id: str,
        *,
        now: datetime | None = None,
    ) -> dict:
        movie_id = _required_identifier(movie_id, "movie_id")
        matches = [
            movie
            for movie in self.catalog(limit=500, now=now)
            if movie["movie_id"] == movie_id
        ]
        if not matches:
            raise ValueError("O filme não está disponível no catálogo atual.")

        previous = self.state()
        if previous["active_hold_id"]:
            release_hold(
                self.connection,
                hold_id=previous["active_hold_id"],
                user_id=self.user_id,
                now=now,
            )

        self._update_state(
            "MOVIE_SELECTED",
            now=now,
            selected_movie_id=movie_id,
        )
        return matches[0]

    def sessions(
        self,
        *,
        cinema_id: str | None = None,
        now: datetime | None = None,
        limit: int = 20,
    ) -> list[dict]:
        current = self.state()
        if not current["selected_movie_id"]:
            raise ValueError("Selecione um filme antes de consultar sessões.")

        return list_session_options(
            self.connection,
            now=now,
            movie_id=current["selected_movie_id"],
            cinema_id=cinema_id,
            limit=limit,
        )

    def select_session(
        self,
        session_id: str,
        *,
        now: datetime | None = None,
    ) -> dict:
        session_id = _required_identifier(session_id, "session_id")
        options = self.sessions(now=now, limit=500)
        selected = next(
            (
                option
                for option in options
                if option["session_id"] == session_id
            ),
            None,
        )
        if selected is None:
            raise ValueError("A sessão não está disponível para o filme.")

        current = self.state()
        if current["active_hold_id"]:
            release_hold(
                self.connection,
                hold_id=current["active_hold_id"],
                user_id=self.user_id,
                now=now,
            )

        self._update_state(
            "SESSION_SELECTED",
            now=now,
            selected_movie_id=current["selected_movie_id"],
            selected_cinema_id=selected["cinema_id"],
            selected_session_id=session_id,
        )
        return selected

    def seat_map(self, *, now: datetime | None = None) -> dict:
        current = self.state()
        if not current["selected_session_id"]:
            raise ValueError("Selecione uma sessão antes de consultar assentos.")

        seats = get_seat_map(
            self.connection,
            session_id=current["selected_session_id"],
            user_id=self.user_id,
            now=now,
        )
        return {"seats": seats, "text": render_text_seat_map(seats)}

    def hold_seats(
        self,
        seat_labels: list[str],
        *,
        now: datetime | None = None,
    ) -> dict:
        current = self.state()
        if not current["selected_session_id"]:
            raise ValueError("Selecione uma sessão antes dos assentos.")

        if current["active_hold_id"]:
            release_hold(
                self.connection,
                hold_id=current["active_hold_id"],
                user_id=self.user_id,
                now=now,
            )

        hold = create_seat_hold(
            self.connection,
            user_id=self.user_id,
            session_id=current["selected_session_id"],
            seat_labels=seat_labels,
            now=now,
        )
        self._update_state(
            "SEATS_HELD",
            now=now,
            selected_movie_id=current["selected_movie_id"],
            selected_cinema_id=current["selected_cinema_id"],
            selected_session_id=current["selected_session_id"],
            active_hold_id=hold.hold_id,
        )
        return {
            "hold_id": hold.hold_id,
            "seat_labels": list(hold.seat_labels),
            "expires_at": hold.expires_at,
        }

    def checkout(
        self,
        ticket_types: dict[str, str],
        *,
        now: datetime | None = None,
    ) -> dict:
        current = self.state()
        if not current["active_hold_id"]:
            raise ValueError("Reserve os assentos antes do checkout.")

        order = create_order(
            self.connection,
            user_id=self.user_id,
            hold_id=current["active_hold_id"],
            ticket_types=ticket_types,
            now=now,
        )
        self._update_state(
            "AWAITING_PAYMENT",
            now=now,
            selected_movie_id=current["selected_movie_id"],
            selected_cinema_id=current["selected_cinema_id"],
            selected_session_id=current["selected_session_id"],
            active_hold_id=current["active_hold_id"],
            active_order_id=order["order_id"],
        )
        return order

    def pay(
        self,
        method: str,
        idempotency_key: str,
        *,
        now: datetime | None = None,
        succeed: bool = True,
    ) -> dict:
        current = self.state()
        if not current["active_order_id"]:
            raise ValueError("Crie o resumo do pedido antes do pagamento.")

        payment = pay_order(
            self.connection,
            user_id=self.user_id,
            order_id=current["active_order_id"],
            method=method,
            idempotency_key=idempotency_key,
            now=now,
            succeed=succeed,
        )

        if payment.status == "SUCCEEDED":
            self._update_state(
                "CONFIRMED",
                now=now,
                selected_movie_id=current["selected_movie_id"],
                selected_cinema_id=current["selected_cinema_id"],
                selected_session_id=current["selected_session_id"],
                active_order_id=current["active_order_id"],
            )

        return {
            "payment_id": payment.payment_id,
            "status": payment.status,
            "method": payment.method,
            "amount_cents": payment.amount_cents,
            "mock_reference": payment.mock_reference,
            "booking_code": payment.booking_code,
        }

    def recent_orders(self, *, limit: int = 10) -> list[dict]:
        return list_user_orders(
            self.connection,
            user_id=self.user_id,
            limit=limit,
        )

    def voucher(self, order_id: str | None = None) -> str:
        if order_id is None:
            order_id = self.state()["active_order_id"]
        if not order_id:
            raise ValueError("Nenhum pedido foi selecionado.")

        order = get_order(
            self.connection,
            order_id=order_id,
            user_id=self.user_id,
        )
        return render_voucher(order)

    def reset(self, *, now: datetime | None = None) -> dict:
        current = self.state()
        if current["active_hold_id"]:
            release_hold(
                self.connection,
                hold_id=current["active_hold_id"],
                user_id=self.user_id,
                now=now,
            )

        return self._update_state("DISCOVERY", now=now)
