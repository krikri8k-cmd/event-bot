#!/usr/bin/env python3
"""
Утилиты для отправки напоминаний о Community событиях
"""

import logging
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from config import load_settings
from database import BotMessage, ChatSettings, CommunityEvent, User, init_engine
from utils.community_participants_service_optimized import get_participants_optimized
from utils.i18n import t
from utils.messaging_utils import send_tracked
from utils.user_language import get_event_description, get_event_title

logger = logging.getLogger(__name__)


def escape_markdown(text: str) -> str:
    """Экранирует специальные символы Markdown"""
    return text.replace("*", "\\*").replace("_", "\\_").replace("`", "\\`").replace("[", "\\[").replace("]", "\\]")


async def _rollback_session_safely(session: AsyncSession, where: str) -> None:
    """Безопасный rollback для очистки состояния 'failed transaction'."""
    try:
        await session.rollback()
    except Exception as e:  # noqa: BLE001
        logger.warning("⚠️ Не удалось выполнить rollback в %s: %s", where, e)


async def get_reminder_lang(session: AsyncSession, chat_id: int, organizer_id: int | None) -> str:
    """Язык для текста напоминания: приоритет chat_settings.default_language → organizer language_code → ru."""
    try:
        r = await session.execute(select(ChatSettings).where(ChatSettings.chat_id == chat_id))
        chat = r.scalar_one_or_none()
        if chat and getattr(chat, "default_language", None) in ("ru", "en"):
            return chat.default_language
        if organizer_id:
            u = await session.execute(select(User).where(User.id == organizer_id))
            user = u.scalar_one_or_none()
            if user and getattr(user, "language_code", None) in ("ru", "en"):
                return user.language_code
    except Exception as e:
        logger.warning(f"get_reminder_lang: {e}")
    return "ru"


def _reminder_card_keyboard(event_id: int, lang: str) -> InlineKeyboardMarkup:
    """Клавиатура Join/Leave для напоминаний (участники уже в тексте сообщения)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("group.card.join", lang),
                    callback_data=f"join_event:{event_id}",
                ),
                InlineKeyboardButton(
                    text=t("group.card.leave", lang),
                    callback_data=f"leave_event:{event_id}",
                ),
            ]
        ]
    )


async def send_event_start_notifications(bot: Bot, session: AsyncSession):
    """
    Отправляет уведомления о начале событий (когда событие начинается)
    """
    try:
        now = datetime.now(UTC)
        # Диапазон: события, которые начались в последние 15 минут (окно для обработки)
        # И события, которые начнутся в ближайшие 15 минут
        # Окно 30 минут (15 назад + 15 вперед) при проверке каждые 5 минут гарантирует, что событие не будет пропущено
        time_min_utc = now - timedelta(minutes=15)
        time_max_utc = now + timedelta(minutes=15)

        logger.info(
            f"🔔 Проверка событий для уведомлений о начале: сейчас UTC={now}, "
            f"ищем события между {time_min_utc} и {time_max_utc} UTC"
        )

        # Открытые Community события (title_en/description_en для i18n напоминаний)
        stmt = (
            select(CommunityEvent)
            .options(
                load_only(
                    CommunityEvent.id,
                    CommunityEvent.chat_id,
                    CommunityEvent.organizer_id,
                    CommunityEvent.organizer_username,
                    CommunityEvent.title,
                    CommunityEvent.title_en,
                    CommunityEvent.description,
                    CommunityEvent.description_en,
                    CommunityEvent.starts_at,
                    CommunityEvent.city,
                    CommunityEvent.location_name,
                    CommunityEvent.location_url,
                    CommunityEvent.status,
                )
            )
            .where(CommunityEvent.status == "open")
            .order_by(CommunityEvent.starts_at)
        )
        result = await session.execute(stmt)
        all_events = result.scalars().all()

        logger.info(f"📊 Запрос к таблице events_community: найдено {len(all_events)} открытых Community событий")

        # Фильтруем события, учитывая часовой пояс города
        from zoneinfo import ZoneInfo

        from utils.simple_timezone import get_city_from_coordinates, get_city_timezone

        events = []
        for event in all_events:
            # Определяем часовой пояс города события
            city = None
            lat = None
            lng = None

            # ПРИОРИТЕТ: Определяем город по координатам из location_url (Google Maps ссылки)
            # Это самый точный способ, так как координаты не врут
            if event.location_url:
                try:
                    from utils.geo_utils import parse_google_maps_link

                    location_data = await parse_google_maps_link(event.location_url)
                    if location_data:
                        lat = location_data.get("lat")
                        lng = location_data.get("lng")
                        if lat and lng:
                            city = get_city_from_coordinates(lat, lng)
                            if city:
                                tz_name = get_city_timezone(city)
                                logger.info(
                                    f"🔍 Событие {event.id}: определен город '{city}' "
                                    f"по координатам из location_url ({lat}, {lng}) -> tz='{tz_name}' "
                                    f"(event.city из БД='{event.city}')"
                                )
                except Exception as e:
                    logger.debug(f"⚠️ Не удалось извлечь координаты из location_url для события {event.id}: {e}")

            # ВАЖНО: Определяем timezone ТОЛЬКО по координатам из location_url
            # Если location_url нет или не удалось извлечь координаты, используем UTC
            # НЕ используем event.city из БД, так как пользователь мог ошибиться в названии
            if not city:
                logger.warning(
                    f"⚠️ Событие {event.id}: не удалось определить город по координатам из location_url, "
                    f"используем UTC (event.city из БД='{event.city}', location_url={bool(event.location_url)})"
                )
                city = None  # Будет использован UTC

            tz_name = get_city_timezone(city) if city else "UTC"
            city_tz = ZoneInfo(tz_name)

            # starts_at - это naive datetime в локальном времени города
            # ВАЖНО: event.starts_at - это TIMESTAMP WITHOUT TIME ZONE (naive datetime)
            # Мы интерпретируем его как local time в часовом поясе города
            # Преобразуем его в UTC для сравнения
            if event.starts_at.tzinfo is not None:
                # Если по какой-то причине starts_at уже имеет timezone, логируем предупреждение
                logger.warning(
                    f"⚠️ Событие {event.id}: starts_at уже имеет timezone: {event.starts_at.tzinfo}, "
                    f"ожидался naive datetime"
                )
                # Используем как есть, если уже aware
                starts_at_utc = event.starts_at.astimezone(UTC)
            else:
                # Naive datetime - интерпретируем как local time в часовом поясе города
                starts_at_local = event.starts_at.replace(tzinfo=city_tz)
                starts_at_utc = starts_at_local.astimezone(UTC)

            # Логируем для отладки определения часового пояса (INFO уровень для важных событий)
            logger.info(
                f"🔍 Событие {event.id} '{event.title[:30]}': city='{city}' -> tz='{tz_name}', "
                f"starts_at={event.starts_at} (local {tz_name}) -> {starts_at_utc} (UTC)"
            )

            # Проверяем, попадает ли событие в диапазон начала
            time_diff_minutes = (starts_at_utc - now).total_seconds() / 60
            if time_min_utc <= starts_at_utc <= time_max_utc:
                events.append(event)
                logger.info(
                    f"🔔 Событие {event.id} '{event.title}': начинается сейчас "
                    f"(starts_at={event.starts_at} ({tz_name}) = {starts_at_utc} UTC, "
                    f"разница: {time_diff_minutes:.1f} минут от сейчас)"
                )
            else:
                # Логируем события, которые близки к началу (в пределах 2 часов) для отладки
                if abs(time_diff_minutes) < 120:
                    logger.info(
                        f"⏭️ Событие {event.id} '{event.title}': не в диапазоне "
                        f"(starts_at={event.starts_at} ({tz_name}) = {starts_at_utc} UTC, "
                        f"разница: {time_diff_minutes:.1f} минут от сейчас, "
                        f"диапазон: {time_min_utc} - {time_max_utc})"
                    )
                # Для событий в пределах 24 часов логируем более подробно
                elif abs(time_diff_minutes) < 1440:
                    logger.debug(
                        f"📅 Событие {event.id} '{event.title[:30]}': "
                        f"starts_at={event.starts_at} ({tz_name}) = {starts_at_utc} UTC, "
                        f"разница: {time_diff_minutes:.1f} минут ({time_diff_minutes/60:.1f} часов) от сейчас"
                    )

        logger.info(f"🔔 Найдено {len(events)} событий для уведомлений о начале (из {len(all_events)} открытых)")

        # Логируем информацию о всех событиях для отладки
        if len(all_events) > 0:
            logger.info(f"📋 Всего открытых событий: {len(all_events)}")
            for event in all_events[:5]:  # Показываем первые 5 для отладки
                # Определяем часовой пояс для этого события
                city = None
                if event.location_url:
                    try:
                        location_data = await parse_google_maps_link(event.location_url)
                        if location_data:
                            lat = location_data.get("lat")
                            lng = location_data.get("lng")
                            if lat and lng:
                                city = get_city_from_coordinates(lat, lng)
                    except Exception:
                        pass
                # ВАЖНО: Определяем timezone ТОЛЬКО по координатам из location_url
                # Если не удалось определить город по координатам, используем UTC
                if not city:
                    logger.warning(
                        f"⚠️ Событие {event.id}: не удалось определить город по координатам из location_url "
                        f"для логирования, используем UTC (event.city из БД='{event.city}', "
                        f"location_url={bool(event.location_url)})"
                    )
                    city = None
                tz_name = get_city_timezone(city) if city else "UTC"
                city_tz = ZoneInfo(tz_name)
                starts_at_local = event.starts_at.replace(tzinfo=city_tz)
                starts_at_utc = starts_at_local.astimezone(UTC)
                time_diff_minutes = (starts_at_utc - now).total_seconds() / 60
                logger.info(
                    f"   📅 Событие {event.id} '{event.title[:30]}': "
                    f"starts_at={event.starts_at} ({tz_name}) = {starts_at_utc} UTC, "
                    f"разница: {time_diff_minutes:.1f} минут от сейчас"
                )

        sent_count = 0
        skipped_count = 0

        for event in events:
            try:
                # Проверяем, не было ли уже отправлено уведомление для этого события
                # Проверяем по event_id, чтобы каждое событие могло получить свое уведомление только один раз
                # Проверяем, есть ли уже уведомление о начале для этого события
                # Используем окно в 2 часа (120 минут) - если уведомление было отправлено в последние 2 часа, пропускаем
                notification_cutoff = now - timedelta(hours=2)
                existing_notification_check = await session.execute(
                    select(BotMessage).where(
                        BotMessage.chat_id == event.chat_id,
                        BotMessage.deleted.is_(False),
                        BotMessage.tag == "event_start",
                        BotMessage.event_id == event.id,
                        BotMessage.created_at >= notification_cutoff,
                    )
                )
                existing_notification = existing_notification_check.scalar_one_or_none()

                if existing_notification:
                    # Если уже есть уведомление для этого события, пропускаем
                    logger.info(
                        f"⏭️ Пропускаем событие {event.id} '{event.title}': "
                        f"уже есть уведомление о начале (отправлено {existing_notification.created_at})"
                    )
                    skipped_count += 1
                    continue

                # Получаем участников (для уведомлений о начале - отправляем даже если нет участников)
                participants = await get_participants_optimized(session, event.id)

                lang = await get_reminder_lang(session, event.chat_id, event.organizer_id)

                # Формируем текст уведомления (язык по чату/организатору)
                _title = get_event_title(event, lang) or event.title or ""
                _desc = get_event_description(event, lang) or event.description or ""
                safe_title = escape_markdown(_title)
                safe_description = escape_markdown(_desc)
                safe_city = escape_markdown(event.city or "")
                safe_username = escape_markdown(event.organizer_username or t("reminder.organizer_unknown", lang))

                # Получаем название места
                location_name = event.location_name or ""
                invalid_names = [
                    "Место проведения",
                    "Место не указано",
                    "Place not specified",
                    "Локация",
                    "Место по ссылке",
                    "Создать",
                    "+ Создать",
                    "",
                ]
                if (
                    location_name in invalid_names
                    or location_name.startswith("+")
                    or location_name.startswith("Создать")
                ):
                    location_name = ""

                if not location_name and event.location_url:
                    try:
                        location_data = await parse_google_maps_link(event.location_url)
                        if location_data and location_data.get("lat") and location_data.get("lng"):
                            from utils.geo_utils import reverse_geocode

                            reverse_name = await reverse_geocode(location_data["lat"], location_data["lng"])
                            if reverse_name:
                                location_name = reverse_name
                    except Exception:
                        pass

                if not location_name:
                    location_name = t("reminder.place_unknown", lang)

                safe_location = escape_markdown(location_name)

                # Формируем список участников для отметки
                mentions = []
                for participant in participants:
                    username = participant.get("username")
                    if username:
                        mentions.append(f"@{username}")

                mentions_text = " ".join(mentions) if mentions else ""

                # Формируем текст сообщения
                notification_text = t("reminder.event_started", lang) + "\n\n"
                notification_text += f"**{safe_title}**\n"

                if safe_city:
                    notification_text += f"🏙️ {safe_city}\n"
                notification_text += f"📍 {safe_location}\n"

                if event.location_url:
                    notification_text += f"🔗 {event.location_url}\n"

                if safe_description:
                    notification_text += f"\n📝 {safe_description}\n"

                notification_text += "\n" + t("reminder.created_by", lang).format(username=safe_username) + "\n\n"

                # Добавляем информацию об участниках только если они есть
                if participants and len(participants) > 0:
                    notification_text += t("reminder.participants", lang).format(count=len(participants)) + "\n"
                    notification_text += mentions_text
                else:
                    notification_text += t("reminder.no_participants", lang) + "\n"

                # Отправляем в группу с кнопками Join/Leave/Участники
                try:
                    reply_markup = _reminder_card_keyboard(event.id, lang)
                    await send_tracked(
                        bot,
                        session,
                        chat_id=event.chat_id,
                        text=notification_text,
                        tag="event_start",
                        event_id=event.id,
                        parse_mode="Markdown",
                        reply_markup=reply_markup,
                    )
                    logger.info(
                        f"✅ Отправлено уведомление о начале события {event.id} '{event.title}' в чат {event.chat_id}"
                    )
                    sent_count += 1

                    import asyncio

                    await asyncio.sleep(1)

                except Exception as e:
                    logger.error(f"❌ Ошибка отправки уведомления о начале для события {event.id}: {e}")
                    continue

            except Exception as e:
                logger.error(f"❌ Ошибка обработки события {event.id}: {e}")
                import traceback

                logger.error(traceback.format_exc())
                continue

        logger.info(f"🔔 Итоги отправки уведомлений о начале: отправлено {sent_count}, пропущено {skipped_count}")

    except Exception as e:  # noqa: BLE001
        await _rollback_session_safely(session, "send_event_start_notifications")
        logger.error(f"❌ Ошибка при отправке уведомлений о начале: {e}")
        import traceback

        logger.error(traceback.format_exc())


async def send_24h_reminders(bot: Bot, session: AsyncSession):
    """
    Отправляет напоминания о событиях, которые начнутся через 24 часа
    Для ВСЕХ событий (с участниками и без)
    """
    logger.info("🔔 === НАЧАЛО send_24h_reminders ===")
    try:
        # Вычисляем временной диапазон: события, которые начнутся через ~24 часа
        # Это позволяет отправлять напоминание один раз, даже если задача запускается несколько раз
        now = datetime.now(UTC)
        target_time = now + timedelta(hours=24)
        logger.info(f"🔔 send_24h_reminders: now={now}, target_time={target_time}")

        # Диапазон: от 23.75 до 24.25 часов (окно в 30 минут)
        # При проверке каждые 30 минут это гарантирует, что событие не будет пропущено
        # и снижает нагрузку на систему по сравнению с проверкой каждые 15 минут
        time_min_utc = target_time - timedelta(minutes=15)
        time_max_utc = target_time + timedelta(minutes=15)

        logger.info(
            f"🔔 Проверка событий для напоминаний: сейчас UTC={now}, "
            f"ищем события между {time_min_utc} и {time_max_utc} UTC (через ~24 часа)"
        )

        # Открытые Community события (title_en/description_en для i18n напоминаний)
        logger.info("🔔 Выполняем запрос к БД для получения открытых Community событий...")
        stmt = (
            select(CommunityEvent)
            .options(
                load_only(
                    CommunityEvent.id,
                    CommunityEvent.chat_id,
                    CommunityEvent.organizer_id,
                    CommunityEvent.organizer_username,
                    CommunityEvent.title,
                    CommunityEvent.title_en,
                    CommunityEvent.description,
                    CommunityEvent.description_en,
                    CommunityEvent.starts_at,
                    CommunityEvent.city,
                    CommunityEvent.location_name,
                    CommunityEvent.location_url,
                    CommunityEvent.status,
                )
            )
            .where(CommunityEvent.status == "open")
            .order_by(CommunityEvent.starts_at)
        )
        result = await session.execute(stmt)
        logger.info("🔔 Запрос к БД выполнен, получаем результаты...")
        all_events = result.scalars().all()
        logger.info(f"📊 Запрос к таблице events_community: найдено {len(all_events)} открытых Community событий")

        # Фильтруем события, учитывая часовой пояс города
        from zoneinfo import ZoneInfo

        from utils.simple_timezone import get_city_from_coordinates, get_city_timezone

        events = []
        for event in all_events:
            # Определяем часовой пояс города события
            # Приоритет: координаты из location_url > название города
            city = None
            lat = None
            lng = None

            # Пытаемся извлечь координаты из location_url (самый надежный способ)
            if event.location_url:
                try:
                    from utils.geo_utils import parse_google_maps_link

                    location_data = await parse_google_maps_link(event.location_url)
                    if location_data:
                        lat = location_data.get("lat")
                        lng = location_data.get("lng")
                        if lat and lng:
                            # Определяем город по координатам (самый точный способ)
                            from utils.simple_timezone import get_city_from_coordinates

                            city = get_city_from_coordinates(lat, lng)
                            if city:
                                tz_name = get_city_timezone(city)
                                logger.info(
                                    f"🔍 Событие {event.id}: определен город '{city}' "
                                    f"(get_city_from_coordinates вернул '{city}') "
                                    f"по координатам из location_url ({lat}, {lng}) -> tz='{tz_name}' "
                                    f"(event.city из БД='{event.city}')"
                                )
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось извлечь координаты из location_url для события {event.id}: {e}")

            # ВАЖНО: Определяем timezone ТОЛЬКО по координатам из location_url
            # Если location_url нет или не удалось извлечь координаты, используем UTC
            # НЕ используем event.city из БД, так как пользователь мог ошибиться в названии
            if not city:
                logger.warning(
                    f"⚠️ Событие {event.id}: не удалось определить город по координатам из location_url, "
                    f"используем UTC (event.city из БД='{event.city}', location_url={bool(event.location_url)})"
                )
                city = None  # Будет использован UTC

            tz_name = get_city_timezone(city) if city else "UTC"
            city_tz = ZoneInfo(tz_name)

            # starts_at - это naive datetime в локальном времени города
            # ВАЖНО: event.starts_at - это TIMESTAMP WITHOUT TIME ZONE (naive datetime)
            # Мы интерпретируем его как local time в часовом поясе города
            # Преобразуем его в UTC для сравнения
            if event.starts_at.tzinfo is not None:
                # Если по какой-то причине starts_at уже имеет timezone, логируем предупреждение
                logger.warning(
                    f"⚠️ Событие {event.id}: starts_at уже имеет timezone: {event.starts_at.tzinfo}, "
                    f"ожидался naive datetime"
                )
                # Используем как есть, если уже aware
                starts_at_utc = event.starts_at.astimezone(UTC)
            else:
                # Naive datetime - интерпретируем как local time в часовом поясе города
                starts_at_local = event.starts_at.replace(tzinfo=city_tz)
                starts_at_utc = starts_at_local.astimezone(UTC)

            # Логируем для отладки определения часового пояса
            time_diff_hours = (starts_at_utc - now).total_seconds() / 3600
            logger.info(
                f"🔍 Событие {event.id} '{event.title[:30]}': city='{city}' -> tz='{tz_name}', "
                f"starts_at={event.starts_at} (local {tz_name}) -> {starts_at_utc} (UTC), "
                f"до начала: {time_diff_hours:.1f} часов"
            )

            # Проверяем, попадает ли событие в диапазон 23.75-24.25 часов от сейчас
            # Детальное логирование для отладки
            is_in_range = time_min_utc <= starts_at_utc <= time_max_utc
            # Логируем ВСЕ события, которые близки к 24-часовой отметке (в пределах 6 часов)
            if 18 <= time_diff_hours <= 30:
                logger.info(
                    f"🔍 Событие {event.id} '{event.title[:30]}': проверка диапазона - "
                    f"starts_at_utc={starts_at_utc}, time_min={time_min_utc}, time_max={time_max_utc}, "
                    f"в диапазоне: {is_in_range}, разница: {time_diff_hours:.2f} часов"
                )

            if is_in_range:
                events.append(event)
                logger.info(
                    f"✅ Событие {event.id} '{event.title}': попадает в окно напоминаний "
                    f"(starts_at={event.starts_at} ({tz_name}) = {starts_at_utc} UTC, "
                    f"до начала: {time_diff_hours:.1f} часов)"
                )
            else:
                # Логируем события, которые близки к 24-часовой отметке (в пределах 4 часов) для отладки
                if 20 <= time_diff_hours <= 28:
                    logger.info(
                        f"⏭️ Событие {event.id} '{event.title}': не в диапазоне напоминаний "
                        f"(starts_at={event.starts_at} ({tz_name}) = {starts_at_utc} UTC, "
                        f"до начала: {time_diff_hours:.1f} часов, "
                        f"диапазон: {time_min_utc} - {time_max_utc})"
                    )

        logger.info(f"🔔 Найдено {len(events)} событий для отправки напоминаний (из {len(all_events)} открытых)")

        sent_count = 0
        skipped_count = 0

        for event in events:
            try:
                # Проверяем, не было ли уже отправлено напоминание для этого конкретного события
                # Теперь проверяем по event_id, чтобы каждое событие могло получить свое напоминание
                from database import BotMessage

                # Проверяем, есть ли уже напоминание для этого события за последние 25 часов
                # (чтобы избежать дубликатов при повторных запусках планировщика)
                reminder_cutoff = now - timedelta(hours=25)
                existing_reminder_check = await session.execute(
                    select(BotMessage).where(
                        BotMessage.chat_id == event.chat_id,
                        BotMessage.deleted.is_(False),
                        BotMessage.tag == "reminder",
                        BotMessage.event_id == event.id,
                        BotMessage.created_at >= reminder_cutoff,
                    )
                )
                existing_reminder = existing_reminder_check.scalar_one_or_none()

                if existing_reminder:
                    # Если уже есть напоминание для этого события, пропускаем
                    logger.info(
                        f"⏭️ Пропускаем событие {event.id} '{event.title}': "
                        f"уже есть напоминание для этого события (отправлено {existing_reminder.created_at})"
                    )
                    skipped_count += 1
                    continue

                # Получаем участников (для напоминаний отправляем даже если нет участников)
                participants = await get_participants_optimized(session, event.id)

                lang = await get_reminder_lang(session, event.chat_id, event.organizer_id)

                # Формируем текст напоминания (язык по чату/организатору)
                _title = get_event_title(event, lang) or event.title or ""
                _desc = get_event_description(event, lang) or event.description or ""
                safe_title = escape_markdown(_title)
                safe_description = escape_markdown(_desc)
                safe_city = escape_markdown(event.city or "")
                safe_username = escape_markdown(event.organizer_username or t("reminder.organizer_unknown", lang))

                # Получаем название места - фильтруем мусорные значения
                location_name = event.location_name or ""
                invalid_names = [
                    "Место проведения",
                    "Место не указано",
                    "Place not specified",
                    "Локация",
                    "Место по ссылке",
                    "Создать",
                    "+ Создать",
                    "",
                ]
                if (
                    location_name in invalid_names
                    or location_name.startswith("+")
                    or location_name.startswith("Создать")
                ):
                    location_name = ""

                # Если location_name пустое, пробуем извлечь из location_url через reverse geocoding
                if not location_name and event.location_url:
                    try:
                        location_data = await parse_google_maps_link(event.location_url)
                        if location_data and location_data.get("lat") and location_data.get("lng"):
                            from utils.geo_utils import reverse_geocode

                            reverse_name = await reverse_geocode(location_data["lat"], location_data["lng"])
                            if reverse_name:
                                location_name = reverse_name
                                logger.info(
                                    f"✅ Получено название места через reverse geocoding "
                                    f"для события {event.id}: {location_name}"
                                )
                    except Exception as e:
                        logger.warning(
                            f"⚠️ Не удалось получить название места из location_url для события {event.id}: {e}"
                        )

                if not location_name:
                    location_name = t("reminder.place_unknown", lang)

                safe_location = escape_markdown(location_name)

                # Форматируем дату и время
                event_time = event.starts_at
                if event_time:
                    date_str = event_time.strftime("%d.%m.%Y")
                    time_str = event_time.strftime("%H:%M")
                    date_at_time = t("reminder.date_at_time", lang).format(date=date_str, time=time_str)
                else:
                    date_str = t("reminder.date_unknown", lang)
                    time_str = ""
                    date_at_time = date_str

                # Формируем список участников для отметки
                mentions = []
                for participant in participants:
                    username = participant.get("username")
                    if username:
                        mentions.append(f"@{username}")

                mentions_text = " ".join(mentions) if mentions else ""

                # Формируем текст сообщения
                reminder_text = t("reminder.24h_title", lang) + "\n\n"
                reminder_text += f"**{safe_title}**\n"
                reminder_text += f"{date_at_time}\n"

                if safe_city:
                    reminder_text += f"🏙️ {safe_city}\n"
                reminder_text += f"📍 {safe_location}\n"

                if event.location_url:
                    reminder_text += f"🔗 {event.location_url}\n"

                if safe_description:
                    reminder_text += f"\n📝 {safe_description}\n"

                reminder_text += "\n" + t("reminder.created_by", lang).format(username=safe_username) + "\n\n"

                if participants and len(participants) > 0:
                    reminder_text += t("reminder.participants", lang).format(count=len(participants)) + "\n"
                    reminder_text += mentions_text
                else:
                    reminder_text += t("reminder.no_participants", lang) + "\n"

                # Отправляем в группу с кнопками Join/Leave/Участники
                try:
                    reply_markup = _reminder_card_keyboard(event.id, lang)
                    await send_tracked(
                        bot,
                        session,
                        chat_id=event.chat_id,
                        text=reminder_text,
                        tag="reminder",
                        event_id=event.id,
                        parse_mode="Markdown",
                        reply_markup=reply_markup,
                    )
                    logger.info(f"✅ Отправлено напоминание о событии {event.id} '{event.title}' в чат {event.chat_id}")
                    sent_count += 1

                    # Небольшая задержка между отправками
                    import asyncio

                    await asyncio.sleep(1)

                except Exception as e:
                    logger.error(f"❌ Ошибка отправки напоминания для события {event.id}: {e}")
                    continue

            except Exception as e:
                logger.error(f"❌ Ошибка обработки события {event.id}: {e}")
                import traceback

                logger.error(traceback.format_exc())
                continue

        logger.info(f"🔔 Итоги отправки напоминаний: отправлено {sent_count}, пропущено {skipped_count}")

    except Exception as e:  # noqa: BLE001
        await _rollback_session_safely(session, "send_24h_reminders")
        logger.error(f"❌ Ошибка при отправке напоминаний: {e}")
        import traceback

        logger.error(traceback.format_exc())


async def send_event_start_notifications_sync(bot_token: str):
    """
    Синхронная обертка для отправки уведомлений о начале событий (для использования в планировщике)
    """
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker

    from database import make_async_engine

    settings = load_settings()
    init_engine(settings.database_url)

    async_engine = make_async_engine(settings.database_url)
    async_session = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    bot = Bot(token=bot_token)

    try:
        async with async_session() as session:
            await send_event_start_notifications(bot, session)
    finally:
        await bot.session.close()
        await async_engine.dispose()


async def send_24h_reminders_sync(bot_token: str):
    """
    Синхронная обертка для отправки напоминаний за 24 часа (для использования в планировщике)
    """
    logger.info("🔔 === НАЧАЛО send_24h_reminders_sync ===")
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker

    from database import make_async_engine

    settings = load_settings()
    init_engine(settings.database_url)

    # Создаем async engine для работы с async сессиями
    # Используем функцию из database.py, которая правильно обрабатывает SSL
    async_engine = make_async_engine(settings.database_url)

    async_session = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    bot = Bot(token=bot_token)

    try:
        async with async_session() as session:
            logger.info("🔔 Вызываем send_24h_reminders...")
            await send_24h_reminders(bot, session)
            logger.info("🔔 === КОНЕЦ send_24h_reminders_sync ===")
    except Exception as e:
        logger.error(f"❌ Ошибка в send_24h_reminders_sync: {e}")
        import traceback

        logger.error(traceback.format_exc())
        raise
    finally:
        await bot.session.close()
        await async_engine.dispose()
