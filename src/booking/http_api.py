"""API HTTP do motor compartilhado de reservas CineMidas."""

import os
from collections.abc import Generator
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .agent_tools import BookingAgentTools
from .checkout import (
    get_order,
    list_user_orders,
    pay_order,
    render_voucher,
)
from .database import connect_database
from .public_catalog import list_public_catalog
from .seat_holds import SeatUnavailableError, get_seat_map, render_text_seat_map
from .session_scheduler import list_session_options
from .traditional_flow import TraditionalBookingFlow


class CheckoutRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=120)
    conversation_id: str = Field(min_length=1, max_length=120)
    movie_id: str = Field(min_length=1, max_length=120)
    session_id: str = Field(min_length=1, max_length=120)
    seat_labels: list[str] = Field(min_length=1, max_length=12)
    half_price_seats: list[str] = Field(default_factory=list, max_length=12)


class PaymentRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=120)
    method: Literal["PIX_MOCK", "CARD_MOCK", "LOYALTY_MOCK"]
    idempotency_key: str = Field(min_length=8, max_length=160)


def _cors_origins() -> list[str]:
    configured = os.getenv(
        "CINEMIDAS_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


def create_booking_api(
    database_path: str | Path,
    *,
    catalog_movies: int | None = None,
) -> FastAPI:
    """Cria a aplicação sem executar coleta ou agendamento implicitamente."""
    database_path = Path(database_path)
    app = FastAPI(
        title="CineMidas Booking API",
        version="2.0.0",
        description=(
            "API educacional de catálogo, sessões e pagamentos simulados."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    def database() -> Generator:
        connection = connect_database(database_path)
        try:
            yield connection
        finally:
            connection.close()

    @app.exception_handler(SeatUnavailableError)
    async def seat_unavailable_handler(_request, error):
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(ValueError)
    async def value_error_handler(_request, error):
        return JSONResponse(status_code=400, content={"detail": str(error)})

    @app.get("/api/v1/health")
    def health():
        return {
            "status": "ok",
            "service": "cinemidas-booking-api",
            "catalog_movies": catalog_movies,
            "payments": "simulated_only",
        }

    @app.get("/api/v1/catalog")
    def catalog(
        limit: int = Query(default=12, ge=1, le=100),
        only_bookable: bool = True,
        connection=Depends(database),
    ):
        return {
            "items": list_public_catalog(
                connection,
                limit=limit,
                only_bookable=only_bookable,
            )
        }

    @app.get("/api/v1/movies/{movie_id}/sessions")
    def movie_sessions(
        movie_id: str,
        limit: int = Query(default=50, ge=1, le=100),
        connection=Depends(database),
    ):
        return {
            "items": list_session_options(
                connection,
                movie_id=movie_id,
                limit=limit,
            )
        }

    @app.get("/api/v1/sessions/{session_id}/seats")
    def session_seats(
        session_id: str,
        user_id: str | None = None,
        connection=Depends(database),
    ):
        seats = get_seat_map(
            connection,
            session_id=session_id,
            user_id=user_id,
        )
        return {"items": seats, "text_map": render_text_seat_map(seats)}

    @app.post("/api/v1/checkout")
    def checkout(request: CheckoutRequest, connection=Depends(database)):
        tools = BookingAgentTools(
            connection,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            channel="WEB",
        )
        tools.select_movie(request.movie_id)
        tools.select_session(request.session_id)
        result = TraditionalBookingFlow(tools).continue_to_checkout(
            request.seat_labels,
            request.half_price_seats,
        )
        return {
            "order": result["order"],
            "hold_expires_at": result["hold"]["expires_at"],
        }

    @app.post("/api/v1/orders/{order_id}/payments")
    def payment(
        order_id: str,
        request: PaymentRequest,
        connection=Depends(database),
    ):
        result = pay_order(
            connection,
            user_id=request.user_id,
            order_id=order_id,
            method=request.method,
            idempotency_key=request.idempotency_key,
        )
        order = get_order(
            connection,
            order_id=order_id,
            user_id=request.user_id,
        )
        return {
            "payment": {
                "payment_id": result.payment_id,
                "status": result.status,
                "method": result.method,
                "amount_cents": result.amount_cents,
                "mock_reference": result.mock_reference,
                "booking_code": result.booking_code,
            },
            "order": order,
            "voucher": render_voucher(order),
        }

    @app.get("/api/v1/users/{user_id}/orders")
    def user_orders(
        user_id: str,
        limit: int = Query(default=10, ge=1, le=50),
        connection=Depends(database),
    ):
        return {
            "items": list_user_orders(
                connection,
                user_id=user_id,
                limit=limit,
            )
        }

    return app
