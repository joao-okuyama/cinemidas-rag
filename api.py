"""Ponto de entrada da API do CineMidas v2."""

import os
from pathlib import Path

import uvicorn

from src.booking.http_api import create_booking_api
from src.booking.runtime import prepare_booking_runtime


DATABASE_PATH = Path(os.getenv("CINEMIDAS_DB_PATH", "data/cinemidas.db"))
TMDB_API_TOKEN = os.getenv("TMDB_API_TOKEN")

runtime_status = prepare_booking_runtime(
    DATABASE_PATH,
    tmdb_token=TMDB_API_TOKEN,
)

app = create_booking_api(
    DATABASE_PATH,
    catalog_movies=runtime_status.catalog_movies,
)


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("API_PORT", "8000")),
    )
