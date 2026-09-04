from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class NormalizedMovie:
    record: dict
    warnings: tuple[str, ...]


def _optional_text(value, field_name: str) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError(
            f"O campo {field_name} deve ser texto ou nulo."
        )

    return value.strip() or None


def _brazil_age_rating(
    payload: dict,
    warnings: list[str],
) -> str | None:
    release_data = payload.get("release_dates")

    if release_data is None:
        warnings.append(
            "Dados de classificação não retornados pelo TMDB."
        )
        return None

    if not isinstance(release_data, dict):
        raise ValueError("release_dates deve ser um objeto.")

    countries = release_data.get("results")

    if not isinstance(countries, list):
        raise ValueError(
            "release_dates.results deve ser uma lista."
        )

    certifications = set()

    for country in countries:
        if not isinstance(country, dict):
            raise ValueError(
                "Registro de país inválido em release_dates."
            )

        if country.get("iso_3166_1") != "BR":
            continue

        releases = country.get("release_dates")

        if not isinstance(releases, list):
            raise ValueError(
                "Os lançamentos brasileiros devem ser uma lista."
            )

        for release in releases:
            if not isinstance(release, dict):
                raise ValueError(
                    "Registro de lançamento brasileiro inválido."
                )

            release_type = release.get("type")

            # Apenas lançamentos cinematográficos:
            # 2 = limitado; 3 = regular.
            if (
                type(release_type) is not int
                or release_type not in (2, 3)
            ):
                continue

            certification = _optional_text(
                release.get("certification"),
                "certification",
            )

            if certification is not None:
                certifications.add(certification)

    if not certifications:
        warnings.append(
            "Classificação cinematográfica brasileira não informada."
        )
        return None

    if len(certifications) > 1:
        warnings.append(
            "Classificações brasileiras divergentes: "
            + ", ".join(sorted(certifications))
            + ". Nenhuma foi selecionada."
        )
        return None

    return next(iter(certifications))


def normalize_tmdb_movie(
    payload: dict,
    *,
    collected_at: datetime,
) -> NormalizedMovie:
    """Transforma detalhes do TMDB em um registro do catálogo.

    Não acessa a rede, não altera o payload e não grava no banco.

    collected_at deve conter fuso horário. A data será convertida
    para UTC e representa a coleta, não a edição do filme no TMDB.
    """
    if not isinstance(payload, dict):
        raise ValueError("Os detalhes do filme devem ser um objeto.")

    movie_id = payload.get("id")

    if type(movie_id) is not int or movie_id <= 0:
        raise ValueError(
            "O identificador TMDB deve ser um inteiro positivo."
        )

    title = _optional_text(payload.get("title"), "title")

    if title is None:
        raise ValueError("O título do filme é obrigatório.")

    if (
        not isinstance(collected_at, datetime)
        or collected_at.tzinfo is None
        or collected_at.utcoffset() is None
    ):
        raise ValueError(
            "collected_at deve ser um datetime com fuso horário."
        )

    warnings = []

    synopsis = _optional_text(
        payload.get("overview"),
        "overview",
    )

    if synopsis is None:
        warnings.append("Sinopse não informada.")

    runtime = payload.get("runtime")

    if (
        type(runtime) is not int
        or runtime <= 0
        or runtime > 9223372036854775807
    ):
        runtime = None
        warnings.append(
            "Duração ausente ou inválida; mantida como desconhecida."
        )

    age_rating = _brazil_age_rating(payload, warnings)

    collected_at_utc = (
        collected_at
        .astimezone(timezone.utc)
        .isoformat(timespec="seconds")
    )

    record = {
        "movie_id": f"TMDB-{movie_id}",
        "provider": "tmdb",
        "provider_movie_id": str(movie_id),
        "title": title,
        "synopsis": synopsis,
        "runtime_minutes": runtime,
        "age_rating": age_rating,
        "source_url": (
            f"https://www.themoviedb.org/movie/{movie_id}"
        ),
        "source_updated_at": collected_at_utc,
    }

    return NormalizedMovie(
        record=record,
        warnings=tuple(warnings),
    )
