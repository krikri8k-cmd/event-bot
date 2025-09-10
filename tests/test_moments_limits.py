#!/usr/bin/env python3
"""
Тесты для системы моментов с лимитами и TTL
"""

import os

# Импортируем функции для тестирования
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot_enhanced_v3 import check_daily_limit, cleanup_expired_moments, create_moment
from config import load_settings


class TestMomentsLimits:
    """Тесты для лимитов моментов"""

    @pytest.fixture
    def mock_session(self):
        """Мок сессии базы данных"""
        session = Mock()
        return session

    @pytest.fixture
    def mock_settings(self):
        """Мок настроек"""
        settings = Mock()
        settings.moment_daily_limit = 2
        settings.moment_ttl_options = [30, 60, 120]
        settings.moment_max_radius_km = 20
        return settings

    @pytest.mark.asyncio
    async def test_daily_limit_not_exceeded(self, mock_session, mock_settings):
        """Тест: лимит не превышен"""
        with (
            patch("bot_enhanced_v3.get_session") as mock_get_session,
            patch("bot_enhanced_v3.load_settings", return_value=mock_settings),
        ):
            mock_get_session.return_value.__enter__.return_value = mock_session
            mock_session.query.return_value.filter.return_value.count.return_value = 1

            can_create, count = await check_daily_limit(12345)

            assert can_create is True
            assert count == 1

    @pytest.mark.asyncio
    async def test_daily_limit_exceeded(self, mock_session, mock_settings):
        """Тест: лимит превышен"""
        with (
            patch("bot_enhanced_v3.get_session") as mock_get_session,
            patch("bot_enhanced_v3.load_settings", return_value=mock_settings),
        ):
            mock_get_session.return_value.__enter__.return_value = mock_session
            mock_session.query.return_value.filter.return_value.count.return_value = 2

            can_create, count = await check_daily_limit(12345)

            assert can_create is False
            assert count == 2

    @pytest.mark.asyncio
    async def test_create_moment_with_limit_check(self, mock_session, mock_settings):
        """Тест: создание момента с проверкой лимита"""
        with (
            patch("bot_enhanced_v3.get_session") as mock_get_session,
            patch("bot_enhanced_v3.load_settings", return_value=mock_settings),
            patch("bot_enhanced_v3.check_daily_limit", return_value=(True, 1)),
        ):
            mock_get_session.return_value.__enter__.return_value = mock_session
            mock_moment = Mock()
            mock_session.add.return_value = None
            mock_session.commit.return_value = None
            mock_session.refresh.return_value = None

            # Мокаем создание объекта Moment
            with patch("bot_enhanced_v3.Moment", return_value=mock_moment):
                moment = await create_moment(
                    user_id=12345,
                    username="testuser",
                    title="Кофе",
                    lat=55.7558,
                    lng=37.6176,
                    ttl_minutes=60,
                )

                assert moment is not None
                mock_session.add.assert_called_once()
                mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_moment_limit_exceeded(self, mock_session, mock_settings):
        """Тест: создание момента при превышении лимита"""
        with (
            patch("bot_enhanced_v3.get_session"),
            patch("bot_enhanced_v3.load_settings", return_value=mock_settings),
            patch("bot_enhanced_v3.check_daily_limit", return_value=(False, 2)),
        ):
            with pytest.raises(ValueError, match="Достигнут лимит: 2 момента в день"):
                await create_moment(
                    user_id=12345,
                    username="testuser",
                    title="Кофе",
                    lat=55.7558,
                    lng=37.6176,
                    ttl_minutes=60,
                )


class TestMomentsTTL:
    """Тесты для TTL моментов"""

    @pytest.fixture
    def mock_session(self):
        """Мок сессии базы данных"""
        session = Mock()
        return session

    @pytest.mark.asyncio
    async def test_cleanup_expired_moments(self, mock_session):
        """Тест: очистка истекших моментов"""
        with patch("bot_enhanced_v3.get_session") as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_session
            mock_session.query.return_value.filter.return_value.update.return_value = 3
            mock_session.commit.return_value = None

            count = await cleanup_expired_moments()

            assert count == 3
            mock_session.commit.assert_called_once()

    def test_ttl_options_parsing(self):
        """Тест: парсинг TTL опций из конфигурации"""
        with patch.dict(os.environ, {"MOMENT_TTL_OPTIONS": "30,60,120"}):
            settings = load_settings()
            assert settings.moment_ttl_options == [30, 60, 120]

    def test_ttl_options_default(self):
        """Тест: дефолтные TTL опции"""
        with patch.dict(os.environ, {}, clear=True):
            settings = load_settings()
            assert settings.moment_ttl_options == [30, 60, 120]


class TestMomentsIntegration:
    """Интеграционные тесты для моментов"""

    @pytest.mark.asyncio
    async def test_moment_creation_flow(self):
        """Тест: полный флоу создания момента"""
        # Этот тест можно расширить для проверки полного процесса
        # создания момента через бота
        pass

    def test_moment_rendering(self):
        """Тест: рендеринг карточки момента"""
        # Тест для проверки правильного отображения карточки момента
        moment_data = {
            "type": "user",
            "title": "Кофе",
            "creator_username": "testuser",
            "expires_utc": (datetime.now(UTC) + timedelta(minutes=45)).isoformat(),
            "lat": 55.7558,
            "lng": 37.6176,
        }

        # Здесь можно добавить проверку рендеринга
        assert moment_data["type"] == "user"
        assert moment_data["creator_username"] == "testuser"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
