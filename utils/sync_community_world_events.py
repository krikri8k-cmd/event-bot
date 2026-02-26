"""
Синхронизация событий Community ↔ World: при редактировании/отмене/возобновлении
в одном месте те же изменения применяются во втором (если событие опубликовано и туда, и туда).
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import CommunityEvent, Event

logger = logging.getLogger(__name__)

EXTERNAL_ID_PREFIX = "community:"


def _parse_community_external_id(external_id: str) -> tuple[int, int] | None:
    """Парсит external_id вида 'community:{chat_id}:{community_event_id}'. Возвращает (chat_id, community_event_id)."""
    if not external_id or not str(external_id).startswith(EXTERNAL_ID_PREFIX):
        return None
    parts = str(external_id).split(":")
    if len(parts) != 3:
        return None
    try:
        return int(parts[1]), int(parts[2])
    except ValueError:
        return None


async def sync_community_event_to_world(session: AsyncSession, chat_id: int, community_event_id: int) -> bool:
    """
    После изменения Community-события обновляет соответствующее событие в World (таблица events),
    если оно было опубликовано туда (source='community', external_id='community:{chat_id}:{id}').
    """
    try:
        community = await session.get(CommunityEvent, community_event_id)
        if not community or community.chat_id != chat_id:
            return False

        external_id = f"{EXTERNAL_ID_PREFIX}{chat_id}:{community_event_id}"
        result = await session.execute(
            select(Event).where(
                Event.source == "community",
                Event.external_id == external_id,
            )
        )
        world = result.scalar_one_or_none()
        if not world:
            logger.debug(
                "sync_community_to_world: world-событие не найдено external_id=%s",
                external_id,
            )
            return False

        # Конвертация времени: Community хранит naive (локальное), World — UTC
        starts_at_utc = community.starts_at
        if community.city:
            try:
                import pytz

                from utils.simple_timezone import get_city_timezone

                tz_name = get_city_timezone(community.city)
                local_tz = pytz.timezone(tz_name)
                local_dt = local_tz.localize(community.starts_at)
                starts_at_utc = local_dt.astimezone(pytz.UTC)
            except Exception as e:
                logger.warning(
                    "sync_community_to_world: не удалось конвертировать время для города %s: %s",
                    community.city,
                    e,
                )

        world.title = community.title or world.title
        world.title_en = community.title_en or world.title_en
        world.description = community.description
        world.description_en = community.description_en
        world.starts_at = starts_at_utc
        world.location_name = community.location_name or world.location_name
        world.location_url = community.location_url
        world.status = community.status
        world.updated_at_utc = datetime.now(UTC)

        await session.commit()
        logger.info(
            "sync_community_to_world: обновлено world event id=%s по community %s",
            world.id,
            community_event_id,
        )
        return True
    except Exception as e:
        logger.exception("sync_community_to_world: %s", e)
        await session.rollback()
        return False


def sync_world_event_to_community(world_event_id: int, session_factory) -> bool:
    """
    После изменения World-события (редактирование/статус) обновляет соответствующее
    Community-событие, если это событие из community (source='community').
    session_factory: callable, возвращающая контекстный менеджер session (например get_session).
    """
    try:
        with session_factory() as session:
            event = session.query(Event).filter(Event.id == world_event_id).first()
            if not event or event.source != "community" or not event.external_id:
                return False

            parsed = _parse_community_external_id(str(event.external_id))
            if not parsed:
                return False
            chat_id, community_event_id = parsed

            community = (
                session.query(CommunityEvent)
                .filter(
                    CommunityEvent.id == community_event_id,
                    CommunityEvent.chat_id == chat_id,
                )
                .first()
            )
            if not community:
                logger.warning(
                    "sync_world_to_community: CommunityEvent %s chat %s не найден",
                    community_event_id,
                    chat_id,
                )
                return False

            # Конвертация времени: World (UTC) -> Community (naive local)
            starts_at_naive = event.starts_at
            if event.starts_at and community.city:
                try:
                    import pytz

                    from utils.simple_timezone import get_city_timezone

                    tz_name = get_city_timezone(community.city)
                    local_tz = pytz.timezone(tz_name)
                    starts_at_naive = event.starts_at.astimezone(local_tz).replace(tzinfo=None)
                except Exception as e:
                    logger.warning(
                        "sync_world_to_community: не удалось конвертировать время: %s",
                        e,
                    )
                    starts_at_naive = event.starts_at.replace(tzinfo=None) if event.starts_at else community.starts_at

            community.title = event.title or community.title
            community.title_en = event.title_en or community.title_en
            community.description = event.description
            community.description_en = event.description_en or community.description_en
            community.starts_at = starts_at_naive
            community.location_name = event.location_name or community.location_name
            community.location_url = event.location_url
            community.status = event.status

            session.commit()
            logger.info(
                "sync_world_to_community: обновлено community event %s по world id=%s",
                community_event_id,
                world_event_id,
            )
            return True
    except Exception as e:
        logger.exception("sync_world_to_community: %s", e)
        return False
