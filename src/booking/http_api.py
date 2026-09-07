"""HTTP boundary: server-issued guests and a shared transactional booking."""
import hashlib
import json
import logging
import os
import secrets
import time
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .agent_tools import BookingAgentTools
from .agent_orchestrator import BookingConversationAgent, GeminiDecisionPlanner
from .checkout import get_order, list_user_orders, pay_order, render_voucher
from .database import connect_database
from .public_catalog import list_public_catalog
from .seat_holds import SeatUnavailableError, expire_holds, get_seat_map, render_text_seat_map
from .session_scheduler import list_session_options
from .traditional_flow import TraditionalBookingFlow
from .transactions import atomic


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SelectionRequest(StrictRequest):
    movie_id: str = Field(min_length=1, max_length=120)
    session_id: str | None = Field(default=None, min_length=1, max_length=120)


class CheckoutRequest(SelectionRequest):
    session_id: str = Field(min_length=1, max_length=120)
    request_id: str = Field(min_length=8, max_length=160)
    seat_labels: list[str] = Field(min_length=1, max_length=12)
    half_price_seats: list[str] = Field(default_factory=list, max_length=12)


class PaymentRequest(StrictRequest):
    method: Literal["PIX_MOCK", "CARD_MOCK", "LOYALTY_MOCK"]
    idempotency_key: str = Field(min_length=8, max_length=160)


class ChatRequest(StrictRequest):
    message: str = Field(min_length=1, max_length=2000)
    request_id: str = Field(min_length=8, max_length=160)


def create_booking_api(database_path: str | Path, *, catalog_movies=None,
                       planner=None, static_directory: str | Path | None = None) -> FastAPI:
    database_path = Path(database_path)
    app = FastAPI(title="CineMidas Booking API", version="2.1.0",
                  description="Cinema e pagamentos simulados. Visitante identificado pelo servidor.")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[x.strip() for x in os.getenv("CINEMIDAS_CORS_ORIGINS",
                       "http://localhost:5173,http://127.0.0.1:5173").split(",") if x.strip()],
        allow_credentials=False, allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @contextmanager
    def database():
        # Open/use/close on the same worker: SQLite's thread check stays enabled.
        connection = connect_database(database_path)
        try:
            yield connection
        finally:
            connection.close()

    def identity(connection, authorization):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "Inicie uma sessão de visitante.")
        token = authorization[7:]
        if not 32 <= len(token) <= 160:
            raise HTTPException(401, "Sessão de visitante inválida.")
        row = connection.execute(
            "SELECT * FROM guest_sessions WHERE token_hash=? AND expires_at>?",
            (hashlib.sha256(token.encode()).hexdigest(), int(time.time())),
        ).fetchone()
        if row is None:
            raise HTTPException(401, "Sessão de visitante expirada. Reabra o site.")
        return BookingAgentTools(connection, user_id=row["user_id"],
                                 conversation_id=row["conversation_id"])

    def snapshot(tools):
        connection = tools.connection
        expire_holds(connection)
        state = tools.state()
        movie = next((m for m in tools.catalog(limit=500)
                      if m["movie_id"] == state["selected_movie_id"]), None)
        session, seats = None, []
        if state["selected_session_id"]:
            row = connection.execute(
                """SELECT s.*, c.name AS cinema_name, c.cinema_id, c.timezone,
                          r.name AS room_name
                   FROM sessions s JOIN rooms r ON r.room_id=s.room_id
                   JOIN cinemas c ON c.cinema_id=r.cinema_id WHERE s.session_id=?""",
                (state["selected_session_id"],),
            ).fetchone()
            if row:
                session = dict(row)
                session["starts_at_local"] = datetime.fromtimestamp(
                    session["starts_at"], tz=ZoneInfo(session["timezone"])).isoformat()
                session["total_full_price_cents"] = session["full_price_cents"] + session["convenience_fee_cents"]
                seats = get_seat_map(connection, session_id=session["session_id"], user_id=tools.user_id)
        order = (get_order(connection, order_id=state["active_order_id"], user_id=tools.user_id)
                 if state["active_order_id"] else None)
        hold = (connection.execute("SELECT expires_at FROM seat_holds WHERE hold_id=?",
                                   (state["active_hold_id"],)).fetchone()
                if state["active_hold_id"] else None)
        return {"state": state, "movie": movie, "session": session,
                "sessions": tools.sessions(limit=100) if state["selected_movie_id"] else [],
                "seats": seats, "order": order, "server_now": int(time.time()),
                "hold_expires_at": hold["expires_at"] if hold else None,
                "voucher": render_voucher(order) if order and order["status"] == "CONFIRMED" else None}

    @app.exception_handler(SeatUnavailableError)
    async def unavailable(_request, error):
        return JSONResponse(status_code=409, content={"detail": str(error), "code": "SEATS_UNAVAILABLE"})

    @app.exception_handler(ValueError)
    async def invalid(_request, error):
        return JSONResponse(status_code=400, content={"detail": str(error)})

    @app.post("/api/v1/guest-session")
    def guest_session(authorization: str | None = Header(default=None)):
        with database() as connection:
            if authorization:
                tools = identity(connection, authorization)
                token = authorization[7:]
            else:
                token = secrets.token_urlsafe(32)
                with atomic(connection):
                    tools = BookingAgentTools(connection, user_id=f"GUEST-{uuid4().hex}",
                                              conversation_id=f"WEB-{uuid4().hex}")
                    connection.execute("INSERT INTO guest_sessions VALUES (?, ?, ?, ?)", (
                        hashlib.sha256(token.encode()).hexdigest(), tools.user_id,
                        tools.conversation_id, int(time.time()) + 30 * 86400))
            return {"token": token, "booking": snapshot(tools)}

    @app.get("/api/v1/health")
    def health():
        with database() as connection:
            connection.execute("SELECT 1").fetchone()
        return {"status": "ok", "service": "cinemidas-booking-api",
                "catalog_movies": catalog_movies, "payments": "simulated_only"}

    @app.get("/api/v1/catalog")
    def catalog(limit: int = Query(default=12, ge=1, le=100), only_bookable: bool = True):
        with database() as connection:
            return {"items": list_public_catalog(connection, limit=limit, only_bookable=only_bookable)}

    @app.get("/api/v1/movies/{movie_id}/sessions")
    def movie_sessions(movie_id: str, limit: int = Query(default=50, ge=1, le=100)):
        with database() as connection:
            return {"items": list_session_options(connection, movie_id=movie_id, limit=limit)}

    @app.get("/api/v1/sessions/{session_id}/seats")
    def session_seats(session_id: str, authorization: str | None = Header(default=None)):
        with database() as connection:
            tools = identity(connection, authorization) if authorization else None
            seats = get_seat_map(connection, session_id=session_id,
                                 user_id=tools.user_id if tools else None)
            return {"items": seats, "text_map": render_text_seat_map(seats)}

    @app.get("/api/v1/booking")
    def booking(authorization: str | None = Header(default=None)):
        with database() as connection:
            return {"booking": snapshot(identity(connection, authorization))}

    @app.post("/api/v1/booking/selection")
    def selection(request: SelectionRequest, authorization: str | None = Header(default=None)):
        with database() as connection:
            tools = identity(connection, authorization)
            with atomic(connection):
                if tools.state()["selected_movie_id"] != request.movie_id:
                    tools.select_movie(request.movie_id)
                if request.session_id and tools.state()["selected_session_id"] != request.session_id:
                    tools.select_session(request.session_id)
                if not request.session_id:
                    tools.remember_options("sessions", tools.sessions(limit=100))
            return {"booking": snapshot(tools)}

    @app.post("/api/v1/booking/reset")
    def reset(authorization: str | None = Header(default=None)):
        with database() as connection:
            tools = identity(connection, authorization)
            tools.reset()
            return {"booking": snapshot(tools)}

    @app.post("/api/v1/checkout")
    def checkout(request: CheckoutRequest, authorization: str | None = Header(default=None)):
        with database() as connection:
            tools = identity(connection, authorization)
            result = TraditionalBookingFlow(tools).continue_to_checkout(
                request.seat_labels, request.half_price_seats, request_id=request.request_id,
                movie_id=request.movie_id, session_id=request.session_id)
            return {**result, "hold_expires_at": result["hold"]["expires_at"], "booking": snapshot(tools)}

    @app.post("/api/v1/orders/{order_id}/payments")
    def payment(order_id: str, request: PaymentRequest, authorization: str | None = Header(default=None)):
        with database() as connection:
            tools = identity(connection, authorization)
            result = pay_order(connection, user_id=tools.user_id, order_id=order_id,
                               method=request.method, idempotency_key=request.idempotency_key)
            order = get_order(connection, order_id=order_id, user_id=tools.user_id)
            return {"payment": asdict(result), "order": order, "voucher": render_voucher(order),
                    "booking": snapshot(tools)}

    @app.get("/api/v1/me/orders")
    def user_orders(limit: int = Query(default=10, ge=1, le=50),
                    authorization: str | None = Header(default=None)):
        with database() as connection:
            tools = identity(connection, authorization)
            expire_holds(connection)
            return {"items": list_user_orders(connection, user_id=tools.user_id, limit=limit)}

    @app.get("/api/v1/agent/history")
    def history(authorization: str | None = Header(default=None)):
        with database() as connection:
            tools = identity(connection, authorization)
            rows = connection.execute(
                """SELECT message, response_json FROM chat_turns WHERE conversation_id=?
                   ORDER BY rowid DESC LIMIT 20""", (tools.conversation_id,)).fetchall()
            return {"items": [{"message": row["message"], "turn": json.loads(row["response_json"])}
                              for row in reversed(rows)]}

    @app.post("/api/v1/agent/chat")
    def chat(request: ChatRequest, authorization: str | None = Header(default=None)):
        message = request.message.strip()
        if not message:
            raise ValueError("Digite uma mensagem.")
        with database() as connection:
            tools = identity(connection, authorization)

            def replay():
                row = connection.execute(
                    "SELECT * FROM chat_turns WHERE conversation_id=? AND request_id=?",
                    (tools.conversation_id, request.request_id)).fetchone()
                if row:
                    if row["message"] != message:
                        raise HTTPException(409, "Esta tentativa já pertence a outra mensagem.")
                    return json.loads(row["response_json"])
                return None

            saved = replay()
            if saved:
                return {"turn": saved, "booking": snapshot(tools)}
            expire_holds(connection)
            agent = BookingConversationAgent(tools, planner or (
                lambda msg, context: GeminiDecisionPlanner(
                    os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"))(msg, context)))
            revision = tools.state()["revision"]
            # Do not hold a SQLite write lock while waiting on Gemini.
            try:
                decision = agent.decide(message)
            except Exception as error:
                logging.getLogger(__name__).warning("Planner failed: %s", type(error).__name__)
                raise HTTPException(503, "A IA está indisponível. Continue sua compra pelos botões.") from None
            with atomic(connection):
                saved = replay()
                if saved:
                    return {"turn": saved, "booking": snapshot(tools)}
                if tools.state()["revision"] != revision:
                    raise HTTPException(409, "A compra mudou durante a resposta. Confira a seleção e tente novamente.")
                try:
                    turn = asdict(agent.execute(message, decision))
                except (TypeError, KeyError) as error:
                    logging.getLogger(__name__).warning("Invalid model arguments: %s", type(error).__name__)
                    raise HTTPException(400, "Não entendi a seleção. Informe filme, sessão ou assentos novamente.") from None
                connection.execute("INSERT INTO chat_turns VALUES (?, ?, ?, ?, ?)", (
                    tools.conversation_id, request.request_id, message,
                    json.dumps(turn, ensure_ascii=False), int(time.time())))
            return {"turn": turn, "booking": snapshot(tools)}

    if static_directory and Path(static_directory).is_dir():
        app.mount("/", StaticFiles(directory=static_directory, html=True), name="website")
    return app
