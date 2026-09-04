"""Fluxo determinístico compartilhado pela compra tradicional do site."""

from uuid import uuid4

from .agent_tools import BookingAgentTools


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
    ) -> dict:
        """Reserva os lugares e calcula o pedido em uma ação do usuário."""
        if not seat_labels:
            raise ValueError("Selecione pelo menos um assento.")

        half_price = set(half_price_seats or [])
        if not half_price.issubset(set(seat_labels)):
            raise ValueError(
                "A meia-entrada deve corresponder a um assento selecionado."
            )

        hold = self.hold(seat_labels)
        order = self.checkout(seat_labels, list(half_price))
        return {"hold": hold, "order": order}

    def pay(self, method: str) -> dict:
        payment = self.tools.pay(
            method,
            idempotency_key=f"SITE-{uuid4().hex}",
        )
        return {"payment": payment, "voucher": self.tools.voucher()}
