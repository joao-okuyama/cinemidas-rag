"""Regras de publicação do catálogo demonstrativo CineViva."""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class CatalogVisibility:
    show_in_catalog: bool
    show_session_options: bool
    reasons: tuple[str, ...]


def _validate_datetime(value: datetime, field_name: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(
            f"{field_name} deve ser um datetime com fuso horário."
        )


def evaluate_catalog_visibility(
    movie: dict,
    *,
    in_latest_collection: bool,
    has_br_theatrical_release: bool,
    has_future_sessions: bool,
    collection_finished_at: datetime,
    now: datetime,
    minimum_runtime: int = 60,
    maximum_collection_age: timedelta = timedelta(hours=48),
) -> CatalogVisibility:
    """Decide se um filme atende à política da vitrine.

    Os indicadores devem ser calculados pelo backend a partir
    da sincronização e das sessões salvas, nunca inventados pelo LLM.

    Esta função não consulta APIs, não acessa o banco
    e não confirma disponibilidade de assentos.

    A idade máxima da coleta é uma regra configurável do produto.
    """
    if not isinstance(movie, dict):
        raise ValueError("movie deve ser um dicionário.")

    indicators = {
        "in_latest_collection": in_latest_collection,
        "has_br_theatrical_release": has_br_theatrical_release,
        "has_future_sessions": has_future_sessions,
    }

    for name, value in indicators.items():
        if type(value) is not bool:
            raise ValueError(f"{name} deve ser booleano.")

    _validate_datetime(collection_finished_at, "collection_finished_at")
    _validate_datetime(now, "now")

    if collection_finished_at > now:
        raise ValueError(
            "A conclusão da coleta não pode estar no futuro."
        )

    if type(minimum_runtime) is not int or minimum_runtime <= 0:
        raise ValueError(
            "minimum_runtime deve ser um inteiro positivo."
        )

    if (
        not isinstance(maximum_collection_age, timedelta)
        or maximum_collection_age <= timedelta(0)
    ):
        raise ValueError(
            "maximum_collection_age deve ser um intervalo positivo."
        )

    reasons = []

    if not in_latest_collection:
        reasons.append("not_in_latest_collection")

    if not has_br_theatrical_release:
        reasons.append("no_br_theatrical_release")

    if now - collection_finished_at > maximum_collection_age:
        reasons.append("stale_collection")

    title = movie.get("title")

    if not isinstance(title, str) or not title.strip():
        reasons.append("missing_title")

    runtime = movie.get("runtime_minutes")

    if type(runtime) is not int or runtime <= 0:
        reasons.append("unknown_runtime")
    elif runtime < minimum_runtime:
        reasons.append("runtime_below_minimum")

    poster_path = movie.get("poster_path")

    if not isinstance(poster_path, str) or not poster_path.strip():
        reasons.append("missing_poster")

    synopsis = movie.get("synopsis")

    if not isinstance(synopsis, str) or not synopsis.strip():
        reasons.append("missing_synopsis")

    show_in_catalog = not reasons

    if not has_future_sessions:
        reasons.append("no_future_sessions")

    return CatalogVisibility(
        show_in_catalog=show_in_catalog,
        show_session_options=(
            show_in_catalog and has_future_sessions
        ),
        reasons=tuple(reasons),
    )


def _popularity_score(movie: dict) -> float:
    """Trata popularidade ausente ou inválida como zero."""
    value = movie.get("popularity")

    if type(value) not in (int, float):
        return 0.0

    try:
        score = float(value)
    except OverflowError:
        return 0.0

    if not math.isfinite(score) or score < 0:
        return 0.0

    return score


def rank_catalog_movies(movies: list[dict]) -> list[dict]:
    """Ordena candidatos já elegíveis por popularidade decrescente.

    Não filtra elegibilidade e não altera a ordem da lista recebida.
    Os dicionários retornados são os mesmos objetos da entrada.

    Popularidade TMDB não representa bilheteria brasileira.
    """
    if not isinstance(movies, list):
        raise ValueError("movies deve ser uma lista.")

    for movie in movies:
        if not isinstance(movie, dict):
            raise ValueError(
                "Cada filme deve ser um dicionário."
            )

        if (
            not isinstance(movie.get("movie_id"), str)
            or not movie["movie_id"].strip()
            or not isinstance(movie.get("title"), str)
            or not movie["title"].strip()
        ):
            raise ValueError(
                "Cada filme deve conter movie_id e title válidos."
            )

    return sorted(
        movies,
        key=lambda movie: (
            -_popularity_score(movie),
            movie["title"].casefold(),
            movie["movie_id"],
        ),
    )
