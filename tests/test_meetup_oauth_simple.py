"""
Простой тест для проверки интеграции OAuth в Meetup API
"""

from unittest.mock import MagicMock, patch


def test_meetup_oauth_headers_integration():
    """Тест: проверяем что MeetupOAuth.headers() правильно интегрирован"""
    from api.oauth_meetup import MeetupOAuth

    # Тест с токенами
    with patch.dict(
        "os.environ",
        {"MEETUP_ACCESS_TOKEN": "test_access_token", "MEETUP_REFRESH_TOKEN": "test_refresh_token"},
    ):
        oauth = MeetupOAuth()
        headers = oauth.headers()
        assert headers == {"Authorization": "Bearer test_access_token"}

    # Тест без токенов
    with patch.dict("os.environ", {}, clear=True):
        oauth = MeetupOAuth()
        headers = oauth.headers()
        assert headers == {}


def test_meetup_fetch_oauth_priority_logic():
    """Тест: проверяем логику приоритета OAuth над API key"""
    from sources.meetup import fetch

    # Мокаем OAuth менеджер с валидными заголовками
    mock_oauth = MagicMock()
    mock_oauth.headers.return_value = {"Authorization": "Bearer oauth_token"}

    with patch("sources.meetup.MeetupOAuth", return_value=mock_oauth):
        with patch("sources.meetup.load_settings") as mock_settings:
            # Настраиваем мок настроек с API key
            mock_settings.return_value.meetup_api_key = "api_key_should_not_be_used"

            # Мокаем httpx.AsyncClient
            with patch("sources.meetup.httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.json.return_value = {"events": []}
                mock_response.raise_for_status.return_value = None

                mock_client_instance = MagicMock()
                mock_client_instance.__aenter__.return_value.get.return_value = mock_response
                mock_client.return_value = mock_client_instance

                # Вызываем fetch
                import asyncio

                asyncio.run(fetch(55.7558, 37.6176, 5.0))

                # Проверяем что запрос был сделан с OAuth заголовками
                mock_client_instance.__aenter__.return_value.get.assert_called_once()
                call_args = mock_client_instance.__aenter__.return_value.get.call_args

                # Проверяем что использовались OAuth заголовки
                headers = call_args[1].get("headers", {})
                assert "Authorization" in headers
                assert headers["Authorization"] == "Bearer oauth_token"

                # Проверяем что API key НЕ был добавлен в параметры
                params = call_args[1].get("params", {})
                assert "key" not in params


def test_meetup_fetch_fallback_to_api_key():
    """Тест: проверяем fallback на API key когда OAuth недоступен"""
    from sources.meetup import fetch

    # Мокаем OAuth менеджер с пустыми заголовками
    mock_oauth = MagicMock()
    mock_oauth.headers.return_value = {}

    with patch("sources.meetup.MeetupOAuth", return_value=mock_oauth):
        with patch("sources.meetup.load_settings") as mock_settings:
            # Настраиваем мок настроек
            mock_settings.return_value.meetup_api_key = "test_api_key"

            # Мокаем httpx.AsyncClient
            with patch("sources.meetup.httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.json.return_value = {"events": []}
                mock_response.raise_for_status.return_value = None

                mock_client_instance = MagicMock()
                mock_client_instance.__aenter__.return_value.get.return_value = mock_response
                mock_client.return_value = mock_client_instance

                # Вызываем fetch
                import asyncio

                asyncio.run(fetch(55.7558, 37.6176, 5.0))

                # Проверяем что запрос был сделан с API key в параметрах
                mock_client_instance.__aenter__.return_value.get.assert_called_once()
                call_args = mock_client_instance.__aenter__.return_value.get.call_args

                # Проверяем что API key был добавлен в параметры
                params = call_args[1].get("params", {})
                assert "key" in params
                assert params["key"] == "test_api_key"
