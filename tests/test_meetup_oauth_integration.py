"""
Тесты для проверки интеграции OAuth в Meetup API
"""

from unittest.mock import MagicMock, patch

# Тесты интеграции OAuth не требуют базы данных
# pytestmark = pytest.mark.api

# В лёгком CI пропускаем модуль целиком
# if os.environ.get("FULL_TESTS") != "1":
#     pytest.skip("Skipping Meetup OAuth integration tests in light CI", allow_module_level=True)


def test_meetup_fetch_uses_oauth_when_available():
    """Тест: Meetup API использует OAuth когда доступен"""
    from sources.meetup import fetch

    # Мокаем OAuth менеджер
    mock_oauth = MagicMock()
    mock_oauth.headers.return_value = {"Authorization": "Bearer test_token"}

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

                # Проверяем что OAuth headers были использованы
                mock_oauth.headers.assert_called_once()

                # Проверяем что запрос был сделан с OAuth заголовками
                mock_client_instance.__aenter__.return_value.get.assert_called_once()
                call_args = mock_client_instance.__aenter__.return_value.get.call_args

                # Проверяем что в заголовках есть Authorization
                headers = call_args[1].get("headers", {})
                assert "Authorization" in headers
                assert headers["Authorization"] == "Bearer test_token"

                # Проверяем что API key НЕ был добавлен в параметры
                params = call_args[1].get("params", {})
                assert "key" not in params


def test_meetup_fetch_fallback_to_api_key_when_oauth_not_available():
    """Тест: Meetup API использует API key когда OAuth недоступен"""
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

                # Проверяем что OAuth headers были проверены
                mock_oauth.headers.assert_called_once()

                # Проверяем что запрос был сделан с API key в параметрах
                mock_client_instance.__aenter__.return_value.get.assert_called_once()
                call_args = mock_client_instance.__aenter__.return_value.get.call_args

                # Проверяем что API key был добавлен в параметры
                params = call_args[1].get("params", {})
                assert "key" in params
                assert params["key"] == "test_api_key"


def test_meetup_fetch_returns_empty_when_no_auth():
    """Тест: Meetup API возвращает пустой список когда нет авторизации"""
    from sources.meetup import fetch

    # Мокаем OAuth менеджер с пустыми заголовками
    mock_oauth = MagicMock()
    mock_oauth.headers.return_value = {}

    with patch("sources.meetup.MeetupOAuth", return_value=mock_oauth):
        with patch("sources.meetup.load_settings") as mock_settings:
            # Настраиваем мок настроек без API key
            mock_settings.return_value.meetup_api_key = None

            # Вызываем fetch
            import asyncio

            result = asyncio.run(fetch(55.7558, 37.6176, 5.0))

            # Проверяем что вернулся пустой список
            assert result == []


def test_meetup_fetch_oauth_priority():
    """Тест: OAuth имеет приоритет над API key"""
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
