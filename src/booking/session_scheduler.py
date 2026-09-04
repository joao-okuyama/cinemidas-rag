"""Programação simulada e consultas de sessões do CineViva."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .public_catalog import list_public_catalog


@dataclass(frozen=True)
class ScheduleResult:
    created_sessions: int
    existing_future_sessions: int
    scheduled_movies: int
    schedule_days: int


ROOM_PRICES = {
    "STANDARD": 3200,
    "VIP": 5200,
    "IMAX": 4800,
}


def _validate_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)

    if (
        not isinstance(now, datetime)
        or now.tzinfo is None
        or now.utcoffset() is None
    ):
        raise ValueError("now deve ser um datetime com fuso horário.")

    return now.astimezone(timezone.utc)


def _ceil_to_half_hour(value: datetime) -> datetime:
    value = value.replace(second=0, microsecond=0)
    remainder = value.minute % 30

    if remainder:
        value += timedelta(minutes=30 - remainder)

    return value


def _timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        raise ValueError(f"Fuso horário desconhecido: {name}.") from None


def generate_demo_sessions(
    connection: sqlite3.Connection,
    *,
    now: datetime | None = None,
    days: int = 7,
    max_movies: int = 8,
    sessions_per_room_day: int = 3,
    turnaround_minutes: int = 15,
    convenience_fee_cents: int = 400,
) -> ScheduleResult:
    """Cria uma programação futura simulada sem substituir sessões existentes.

    Uma nova execução é idempotente enquanto houver sessões futuras. A função
    nunca apaga sessões, o que preservará referências de reservas e pedidos.
    """
    now = _validate_now(now)

    integer_options = {
        "days": days,
        "max_movies": max_movies,
        "sessions_per_room_day": sessions_per_room_day,
        "turnaround_minutes": turnaround_minutes,
        "convenience_fee_cents": convenience_fee_cents,
    }

    for name, value in integer_options.items():
        if type(value) is not int:
            raise ValueError(f"{name} deve ser inteiro.")

    if days <= 0 or max_movies <= 0 or sessions_per_room_day <= 0:
        raise ValueError("Dias, filmes e sessões devem ser positivos.")

    if turnaround_minutes < 0 or convenience_fee_cents < 0:
        raise ValueError("Intervalo e taxa não podem ser negativos.")

    now_epoch = int(now.timestamp())
    existing = connection.execute(
        """
        SELECT COUNT(*)
        FROM sessions
        WHERE status = 'SCHEDULED' AND starts_at > ?
        """,
        (now_epoch,),
    ).fetchone()[0]

    if existing:
        movie_count = connection.execute(
            """
            SELECT COUNT(DISTINCT movie_id)
            FROM sessions
            WHERE status = 'SCHEDULED' AND starts_at > ?
            """,
            (now_epoch,),
        ).fetchone()[0]

        return ScheduleResult(0, existing, movie_count, days)

    movies = list_public_catalog(
        connection,
        now=now,
        limit=max_movies,
        only_bookable=False,
    )

    if not movies:
        raise RuntimeError(
            "Nenhum filme elegível foi encontrado na coleta atual."
        )

    rooms = connection.execute(
        """
        SELECT
            r.room_id,
            r.category,
            c.timezone,
            GROUP_CONCAT(rf.projection_format) AS formats
        FROM rooms AS r
        JOIN cinemas AS c ON c.cinema_id = r.cinema_id
        JOIN room_formats AS rf ON rf.room_id = r.room_id
        GROUP BY r.room_id, r.category, c.timezone
        ORDER BY r.room_id
        """
    ).fetchall()

    if not rooms:
        raise RuntimeError("Nenhuma sala CineViva foi configurada.")

    planned = []

    for room_index, room in enumerate(rooms):
        cinema_timezone = _timezone(room["timezone"])
        local_now = now.astimezone(cinema_timezone)
        formats = set(room["formats"].split(","))

        for day_offset in range(days):
            schedule_date = local_now.date() + timedelta(days=day_offset)
            cursor = datetime.combine(
                schedule_date,
                time(hour=13),
                tzinfo=cinema_timezone,
            )

            if day_offset == 0:
                cursor = max(
                    cursor,
                    _ceil_to_half_hour(local_now + timedelta(minutes=60)),
                )

            final_start = datetime.combine(
                schedule_date,
                time(hour=23),
                tzinfo=cinema_timezone,
            )

            for slot_index in range(sessions_per_room_day):
                movie_index = (
                    room_index + day_offset + slot_index
                ) % len(movies)
                movie = movies[movie_index]
                runtime = movie["runtime_minutes"]
                ends_at = cursor + timedelta(minutes=runtime)

                if cursor > final_start or ends_at.date() != schedule_date:
                    break

                projection_format = "2D"
                if "3D" in formats and movie_index % 3 == 0:
                    projection_format = "3D"

                audio_version = (
                    "DUBBED" if slot_index % 2 == 0 else "SUBTITLED"
                )
                base_price = ROOM_PRICES[room["category"]]
                if projection_format == "3D":
                    base_price += 600

                starts_epoch = int(
                    cursor.astimezone(timezone.utc).timestamp()
                )
                ends_epoch = starts_epoch + runtime * 60
                available_epoch = (
                    ends_epoch + turnaround_minutes * 60
                )
                session_id = (
                    f"CV-SES-{schedule_date:%Y%m%d}-"
                    f"{room['room_id'][-3:]}-{cursor:%H%M}"
                )

                planned.append(
                    (
                        session_id,
                        movie["movie_id"],
                        room["room_id"],
                        projection_format,
                        audio_version,
                        "SCHEDULED",
                        starts_epoch,
                        runtime,
                        turnaround_minutes,
                        ends_epoch,
                        available_epoch,
                        base_price,
                        convenience_fee_cents,
                    )
                )

                cursor = _ceil_to_half_hour(
                    ends_at + timedelta(minutes=turnaround_minutes)
                )

    if not planned:
        raise RuntimeError(
            "Não foi possível encaixar sessões na janela operacional."
        )

    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.executemany(
            """
            INSERT INTO sessions (
                session_id, movie_id, room_id, projection_format,
                audio_version, status, starts_at, runtime_minutes,
                turnaround_minutes, ends_at, room_available_at,
                full_price_cents, convenience_fee_cents
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            planned,
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise

    return ScheduleResult(
        created_sessions=len(planned),
        existing_future_sessions=0,
        scheduled_movies=len({row[1] for row in planned}),
        schedule_days=days,
    )


def list_session_options(
    connection: sqlite3.Connection,
    *,
    now: datetime | None = None,
    movie_id: str | None = None,
    cinema_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Lista sessões futuras com horário convertido para o fuso da unidade."""
    now = _validate_now(now)

    if movie_id is not None and (
        not isinstance(movie_id, str) or not movie_id.strip()
    ):
        raise ValueError("movie_id deve ser texto preenchido ou nulo.")

    if cinema_id is not None and (
        not isinstance(cinema_id, str) or not cinema_id.strip()
    ):
        raise ValueError("cinema_id deve ser texto preenchido ou nulo.")

    if type(limit) is not int or limit <= 0:
        raise ValueError("limit deve ser um inteiro positivo.")

    clauses = ["s.status = 'SCHEDULED'", "s.starts_at > ?"]
    parameters = [int(now.timestamp())]

    if movie_id is not None:
        clauses.append("s.movie_id = ?")
        parameters.append(movie_id.strip())

    if cinema_id is not None:
        clauses.append("c.cinema_id = ?")
        parameters.append(cinema_id.strip())

    parameters.append(limit)

    rows = connection.execute(
        f"""
        SELECT
            s.session_id,
            s.movie_id,
            m.title AS movie_title,
            c.cinema_id,
            c.name AS cinema_name,
            c.region,
            c.timezone,
            r.room_id,
            r.name AS room_name,
            r.category AS room_category,
            s.projection_format,
            s.audio_version,
            s.starts_at,
            s.ends_at,
            s.full_price_cents,
            s.convenience_fee_cents
        FROM sessions AS s
        JOIN movies AS m ON m.movie_id = s.movie_id
        JOIN rooms AS r ON r.room_id = s.room_id
        JOIN cinemas AS c ON c.cinema_id = r.cinema_id
        WHERE {' AND '.join(clauses)}
        ORDER BY s.starts_at, c.cinema_id, r.room_id
        LIMIT ?
        """,
        parameters,
    ).fetchall()

    options = []

    for row in rows:
        option = dict(row)
        cinema_timezone = _timezone(option["timezone"])
        option["starts_at_local"] = datetime.fromtimestamp(
            option["starts_at"],
            tz=timezone.utc,
        ).astimezone(cinema_timezone).isoformat(timespec="minutes")
        option["ends_at_local"] = datetime.fromtimestamp(
            option["ends_at"],
            tz=timezone.utc,
        ).astimezone(cinema_timezone).isoformat(timespec="minutes")
        option["total_full_price_cents"] = (
            option["full_price_cents"]
            + option["convenience_fee_cents"]
        )
        options.append(option)

    return options
