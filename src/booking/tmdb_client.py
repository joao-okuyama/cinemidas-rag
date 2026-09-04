import requests


BASE_URL = "https://api.themoviedb.org/3"


class TMDBError(RuntimeError):
    """Erro de comunicação ou resposta inesperada do TMDB."""


class TMDBClient:
    def __init__(self, token: str):
        if not isinstance(token, str) or not token.strip():
            raise ValueError("O token do TMDB é obrigatório.")

        self._token = token.strip()

    def _get_json(self, path: str, params: dict) -> dict:
        try:
            response = requests.get(
                f"{BASE_URL}{path}",
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "accept": "application/json",
                },
                params=params,
                timeout=30,
            )
        except requests.RequestException:
            raise TMDBError(
                "Não foi possível conectar ao TMDB."
            ) from None

        try:
            if response.status_code != 200:
                # Não inclui token, cabeçalhos ou corpo da resposta.
                raise TMDBError(
                    "A consulta ao TMDB falhou. "
                    f"Status HTTP: {response.status_code}."
                )

            try:
                payload = response.json()
            except ValueError:
                raise TMDBError(
                    "O TMDB retornou um JSON inválido."
                ) from None

            if not isinstance(payload, dict):
                raise TMDBError(
                    "O TMDB retornou um formato inesperado."
                )

            return payload

        finally:
            response.close()

    def get_now_playing_page(self, page: int = 1) -> dict:
        """Consulta uma página do catálogo cinematográfico para BR.

        O chamador é responsável por percorrer as demais páginas.
        A resposta não comprova sessões em um cinema específico.
        """
        if type(page) is not int or page < 1:
            raise ValueError(
                "A página deve ser um inteiro positivo."
            )

        payload = self._get_json(
            "/movie/now_playing",
            params={
                "language": "pt-BR",
                "region": "BR",
                "page": page,
            },
        )

        results = payload.get("results")
        total_pages = payload.get("total_pages")
        returned_page = payload.get("page")

        if (
            not isinstance(results, list)
            or type(total_pages) is not int
            or total_pages < 0
            or type(returned_page) is not int
            or returned_page != page
        ):
            raise TMDBError(
                "A estrutura da página de filmes é inválida."
            )

        for movie in results:
            if (
                not isinstance(movie, dict)
                or type(movie.get("id")) is not int
                or movie["id"] <= 0
            ):
                raise TMDBError(
                    "A página contém um filme sem identificador válido."
                )

        return payload

    def get_movie_details(self, movie_id: int) -> dict:
        """Busca detalhes e registros de lançamento de um filme.

        Campos ausentes não são preenchidos artificialmente.
        A classificação brasileira será extraída na normalização.
        """
        if type(movie_id) is not int or movie_id < 1:
            raise ValueError(
                "O identificador do filme deve ser um inteiro positivo."
            )

        payload = self._get_json(
            f"/movie/{movie_id}",
            params={
                "language": "pt-BR",
                "append_to_response": "release_dates",
            },
        )

        returned_id = payload.get("id")

        if type(returned_id) is not int or returned_id != movie_id:
            raise TMDBError(
                "Os detalhes não correspondem ao filme solicitado."
            )

        return payload
