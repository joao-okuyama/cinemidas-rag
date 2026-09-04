"""Testes do cliente TMDB sem chamadas externas."""

import unittest
from unittest.mock import Mock, patch

import requests

from src.booking.tmdb_client import TMDBClient, TMDBError


class TMDBClientTests(unittest.TestCase):
    def setUp(self):
        # Valor fictício, usado exclusivamente nos testes.
        self.token = "TEST-TOKEN-NOT-REAL"
        self.client = TMDBClient(f"  {self.token}  ")

        patcher = patch(
            "src.booking.tmdb_client.requests.get"
        )
        self.mock_get = patcher.start()
        self.addCleanup(patcher.stop)

        self.response = Mock()
        self.response.status_code = 200
        self.mock_get.return_value = self.response

    def page_payload(self, **overrides):
        payload = {
            "page": 1,
            "total_pages": 2,
            "results": [
                {
                    "id": 101,
                    "title": "Filme fictício",
                }
            ],
        }
        payload.update(overrides)
        return payload

    def test_empty_or_invalid_token_is_rejected(self):
        for token in (None, "", "   ", 123):
            with self.subTest(token=token):
                with self.assertRaises(ValueError):
                    TMDBClient(token)

        self.mock_get.assert_not_called()

    def test_invalid_page_is_rejected_without_request(self):
        for page in (0, -1, 1.5, "1", True, None):
            with self.subTest(page=page):
                with self.assertRaises(ValueError):
                    self.client.get_now_playing_page(page)

        self.mock_get.assert_not_called()

    def test_invalid_movie_id_is_rejected_without_request(self):
        for movie_id in (0, -1, 1.5, "101", True, None):
            with self.subTest(movie_id=movie_id):
                with self.assertRaises(ValueError):
                    self.client.get_movie_details(movie_id)

        self.mock_get.assert_not_called()

    def test_now_playing_request_uses_expected_parameters(self):
        payload = self.page_payload(page=2)
        self.response.json.return_value = payload

        result = self.client.get_now_playing_page(page=2)

        self.assertEqual(result, payload)

        self.mock_get.assert_called_once_with(
            "https://api.themoviedb.org/3/movie/now_playing",
            headers={
                "Authorization": f"Bearer {self.token}",
                "accept": "application/json",
            },
            params={
                "language": "pt-BR",
                "region": "BR",
                "page": 2,
            },
            timeout=30,
        )

        self.response.close.assert_called_once()

    def test_details_request_includes_release_dates(self):
        payload = {
            "id": 101,
            "title": "Filme fictício",
            "runtime": 120,
            "release_dates": {"results": []},
        }
        self.response.json.return_value = payload

        result = self.client.get_movie_details(101)

        self.assertEqual(result, payload)

        self.mock_get.assert_called_once_with(
            "https://api.themoviedb.org/3/movie/101",
            headers={
                "Authorization": f"Bearer {self.token}",
                "accept": "application/json",
            },
            params={
                "language": "pt-BR",
                "append_to_response": "release_dates",
            },
            timeout=30,
        )

        self.response.close.assert_called_once()

    def test_network_errors_are_replaced_by_safe_messages(self):
        for exception_class in (
            requests.Timeout,
            requests.ConnectionError,
        ):
            with self.subTest(error=exception_class.__name__):
                self.mock_get.side_effect = exception_class(
                    f"Detalhe sensível: {self.token}"
                )

                with self.assertRaises(TMDBError) as caught:
                    self.client.get_movie_details(101)

                message = str(caught.exception)

                self.assertIn("conectar", message)
                self.assertNotIn(self.token, message)
                self.assertNotIn("Detalhe sensível", message)

    def test_http_errors_are_reported_without_response_body(self):
        for status in (401, 403, 404, 429, 500):
            with self.subTest(status=status):
                self.response.reset_mock()
                self.response.status_code = status
                self.response.text = (
                    f"Corpo sensível: {self.token}"
                )

                with self.assertRaises(TMDBError) as caught:
                    self.client.get_movie_details(101)

                message = str(caught.exception)

                self.assertIn(str(status), message)
                self.assertNotIn(self.token, message)
                self.assertNotIn("Corpo sensível", message)

                self.response.json.assert_not_called()
                self.response.close.assert_called_once()

    def test_invalid_json_is_rejected_and_response_is_closed(self):
        self.response.json.side_effect = ValueError(
            "Resposta não JSON"
        )

        with self.assertRaisesRegex(TMDBError, "JSON inválido"):
            self.client.get_movie_details(101)

        self.response.close.assert_called_once()

    def test_non_object_json_is_rejected(self):
        for payload in ([], None, "texto", 123):
            with self.subTest(payload=payload):
                self.response.reset_mock()
                self.response.json.return_value = payload

                with self.assertRaisesRegex(
                    TMDBError,
                    "formato inesperado",
                ):
                    self.client.get_movie_details(101)

                self.response.close.assert_called_once()

    def test_invalid_pagination_structure_is_rejected(self):
        invalid_fields = [
            {"results": None},
            {"results": {}},
            {"total_pages": -1},
            {"total_pages": "2"},
            {"total_pages": True},
            {"page": 2},
            {"page": "1"},
            {"page": True},
        ]

        for fields in invalid_fields:
            with self.subTest(fields=fields):
                self.response.json.return_value = (
                    self.page_payload(**fields)
                )

                with self.assertRaisesRegex(
                    TMDBError,
                    "estrutura da página",
                ):
                    self.client.get_now_playing_page()

    def test_invalid_movie_entries_are_rejected(self):
        invalid_entries = [
            None,
            "filme",
            {},
            {"id": 0},
            {"id": -1},
            {"id": "101"},
            {"id": True},
        ]

        for entry in invalid_entries:
            with self.subTest(entry=entry):
                self.response.json.return_value = (
                    self.page_payload(results=[entry])
                )

                with self.assertRaisesRegex(
                    TMDBError,
                    "identificador válido",
                ):
                    self.client.get_now_playing_page()

    def test_details_must_match_requested_movie_id(self):
        for returned_id in (102, "101", None, True):
            with self.subTest(returned_id=returned_id):
                self.response.json.return_value = {
                    "id": returned_id,
                }

                with self.assertRaisesRegex(
                    TMDBError,
                    "não correspondem",
                ):
                    self.client.get_movie_details(101)

    def test_missing_optional_metadata_is_not_invented(self):
        self.response.json.return_value = {"id": 101}

        result = self.client.get_movie_details(101)

        self.assertEqual(result, {"id": 101})
        self.assertNotIn("runtime", result)
        self.assertNotIn("release_dates", result)
        self.assertNotIn("overview", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
