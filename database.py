from __future__ import annotations

import logging

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Text,
    create_engine,
    func,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, sessionmaker

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=convention)
Base = declarative_base(metadata=metadata)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(255))
    user_tz: Mapped[str | None] = mapped_column(String(64))
    default_radius_km: Mapped[int] = mapped_column(Integer, default=5)
    last_lat: Mapped[float | None] = mapped_column(Float)
    last_lng: Mapped[float | None] = mapped_column(Float)
    last_geo_at_utc: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    created_at_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at_utc: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    events_created_ids: Mapped[str | None] = mapped_column(Text)
    events_joined_ids: Mapped[str | None] = mapped_column(Text)
    rockets_balance: Mapped[int] = mapped_column(Integer, default=0)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(20), nullable=False)  # 'body' или 'spirit'
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    location_url: Mapped[str | None] = mapped_column(String(500))
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)  # порядок показа (1-15)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserTask(Base):
    __tablename__ = "user_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active")  # 'active', 'completed', 'cancelled', 'expired'
    feedback: Mapped[str | None] = mapped_column(Text)
    accepted_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str | None] = mapped_column(
        String(64), index=True
    )  # источник события (ics.bali, nexudus.jakarta, etc)
    external_id: Mapped[str | None] = mapped_column(String(64), index=True)  # уникальный ID из источника
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    time_local: Mapped[str | None] = mapped_column(String(16))  # YYYY-MM-DD HH:MM
    event_tz: Mapped[str | None] = mapped_column(String(64))
    time_utc: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))  # legacy, используем starts_at
    starts_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))  # время начала события
    ends_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))  # время окончания события
    url: Mapped[str | None] = mapped_column(Text)  # ссылка на событие
    location_name: Mapped[str | None] = mapped_column(String(255))
    location_url: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    organizer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    organizer_username: Mapped[str | None] = mapped_column(String(255))
    chat_id: Mapped[int | None] = mapped_column(BigInteger, index=True)  # ID чата, где создано событие
    max_participants: Mapped[int | None] = mapped_column(Integer)
    participants_ids: Mapped[str | None] = mapped_column(Text)
    current_participants: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    created_at_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at_utc: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    community_name: Mapped[str | None] = mapped_column(String(120))
    community_link: Mapped[str | None] = mapped_column(Text)
    is_generated_by_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    dedupe_key: Mapped[str | None] = mapped_column(String(64), index=True)


# Класс Moment удален - функция Moments отключена
# class Moment(Base):
#     __tablename__ = "moments"
#     ... (удален)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_user_id: Mapped[int] = mapped_column(BigInteger)
    from_user_id: Mapped[int] = mapped_column(BigInteger)
    context_type: Mapped[str] = mapped_column(String(16))
    context_id: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(String(64))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(16), default="new")


class TaskPlace(Base):
    __tablename__ = "task_places"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(20), nullable=False)  # 'body', 'spirit', 'career', 'social'
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    google_maps_url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TaskTemplate(Base):
    __tablename__ = "task_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(20), nullable=False)  # 'body', 'spirit', 'career', 'social'
    place_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'park', 'cafe', 'library', etc.
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    rocket_value: Mapped[int] = mapped_column(Integer, default=1)
    created_at_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DailyView(Base):
    __tablename__ = "daily_views"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    view_type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'template', 'place'
    view_key: Mapped[str] = mapped_column(String(100), nullable=False)  # template_id или place_id
    view_date: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# === МОДЕЛИ ДЛЯ ГРУППОВЫХ ЧАТОВ (ИЗОЛИРОВАННЫЙ МОДУЛЬ) ===


class CommunityEvent(Base):
    """События в групповых чатах (изолированно от основного бота)"""

    __tablename__ = "events_community"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    organizer_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    organizer_username: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    starts_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    city: Mapped[str | None] = mapped_column(String(64))
    location_name: Mapped[str | None] = mapped_column(String(255))
    location_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BotMessage(Base):
    """Трекинг всех сообщений бота в групповых чатах для функции 'Спрятать бота'"""

    __tablename__ = "bot_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tag: Mapped[str] = mapped_column(String(50), default="service", index=True)  # panel, service, notification
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatSettings(Base):
    """Настройки групповых чатов"""

    __tablename__ = "chat_settings"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    last_panel_message_id: Mapped[int | None] = mapped_column(BigInteger)
    muted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


engine: Engine | None = None
Session: sessionmaker | None = None


def make_engine(database_url: str) -> Engine:
    # Normalize URL to sync psycopg2 dialect
    if database_url.startswith("postgresql+asyncpg://"):
        database_url = database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    elif database_url.startswith("postgresql+psycopg://"):
        database_url = database_url.replace("postgresql+psycopg://", "postgresql+psycopg2://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    elif database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)
    return create_engine(database_url, future=True, pool_pre_ping=True)


def init_engine(database_url: str) -> None:
    global engine, Session
    if engine is None:
        try:
            engine = make_engine(database_url)
            # Test connection immediately to fail fast
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            Session = sessionmaker(bind=engine, expire_on_commit=False)
        except Exception:
            logging.exception("Не удалось подключиться к базе данных по URL: %s", database_url)
            raise RuntimeError("Не удалось подключиться к базе данных.")


def create_all() -> None:
    assert engine is not None
    Base.metadata.create_all(bind=engine)


def get_engine() -> Engine:
    """Возвращает глобальный engine"""
    if engine is None:
        raise RuntimeError("Engine not initialized. Call init_engine() first.")
    return engine


def get_session():
    assert Session is not None
    return Session()


async def get_async_session():
    """Асинхронная версия сессии для совместимости с async функциями"""
    assert Session is not None
    return Session()


def _csv_to_set(csv_value: str | None) -> set[int]:
    if not csv_value:
        return set()
    result: set[int] = set()
    for part in csv_value.split(","):
        part = part.strip()
        if part:
            try:
                result.add(int(part))
            except ValueError:
                continue
    return result


def _set_to_csv(values: set[int]) -> str:
    return ",".join(str(v) for v in sorted(values))


def rsvp_event(session, event_id: int, user_id: int, join: bool):
    event = session.get(Event, event_id)
    if not event:
        raise ValueError("Event not found")
    participants = _csv_to_set(event.participants_ids)
    if join:
        participants.add(user_id)
    else:
        participants.discard(user_id)

    event.participants_ids = _set_to_csv(participants)
    event.current_participants = len(participants)

    max_p = event.max_participants or 0
    if max_p > 0 and event.current_participants >= max_p:
        event.status = "closed"
    elif event.status == "closed" and (max_p == 0 or event.current_participants < max_p):
        event.status = "open"

    session.flush()
    return event
