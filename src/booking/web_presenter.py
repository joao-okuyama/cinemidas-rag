"""Apresentação HTML dos dados já validados pelo backend."""

from html import escape


def render_catalog_cards(movies: list[dict]) -> str:
    if not movies:
        return '<p class="empty-state">Nenhum filme encontrado.</p>'

    cards = []
    for movie in movies:
        title = escape(str(movie["title"]))
        genres = escape(", ".join(movie["genres"]) or "Gênero não informado")
        rating = escape(str(movie["age_rating"] or "Não informada"))
        runtime = movie["runtime_minutes"]
        runtime_text = f"{runtime} min" if runtime else "Duração não informada"
        poster_url = movie.get("poster_url")

        if poster_url:
            poster = (
                f'<img src="{escape(poster_url, quote=True)}" '
                f'alt="Pôster de {title}" loading="lazy">'
            )
        else:
            poster = '<div class="poster-fallback">🎬</div>'

        availability = (
            '<span class="available">Sessões disponíveis</span>'
            if movie.get("show_session_options")
            else '<span class="unavailable">Em breve</span>'
        )

        cards.append(
            '<article class="movie-card">'
            f'{poster}<div class="movie-info"><h3>{title}</h3>'
            f'<p>{genres}</p><p>{escape(runtime_text)} · Classificação {rating}</p>'
            f'{availability}</div></article>'
        )

    return '<div class="movie-grid">' + "".join(cards) + "</div>"
