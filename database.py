from __future__ import annotations

from typing import Optional

import logging
from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, MetaData, String, Text, func, create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, Mapped, mapped_column, sessionmaker


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
	username: Mapped[Optional[str]] = mapped_column(String(255))
	full_name: Mapped[Optional[str]] = mapped_column(String(255))
	user_tz: Mapped[Optional[str]] = mapped_column(String(64))
	default_radius_km: Mapped[int] = mapped_column(Integer, default=4)
	last_lat: Mapped[Optional[float]] = mapped_column(Float)
	last_lng: Mapped[Optional[float]] = mapped_column(Float)
	last_geo_at_utc: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True))
	created_at_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	updated_at_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
	events_created_ids: Mapped[Optional[str]] = mapped_column(Text)
	events_joined_ids: Mapped[Optional[str]] = mapped_column(Text)


class Event(Base):
	__tablename__ = "events"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	title: Mapped[str] = mapped_column(String(120), nullable=False)
	description: Mapped[Optional[str]] = mapped_column(Text)
	time_local: Mapped[Optional[str]] = mapped_column(String(16))  # YYYY-MM-DD HH:MM
	event_tz: Mapped[Optional[str]] = mapped_column(String(64))
	time_utc: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True))
	location_name: Mapped[Optional[str]] = mapped_column(String(255))
	location_url: Mapped[Optional[str]] = mapped_column(Text)
	lat: Mapped[Optional[float]] = mapped_column(Float)
	lng: Mapped[Optional[float]] = mapped_column(Float)
	organizer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
	organizer_username: Mapped[Optional[str]] = mapped_column(String(255))
	max_participants: Mapped[Optional[int]] = mapped_column(Integer)
	participants_ids: Mapped[Optional[str]] = mapped_column(Text)
	current_participants: Mapped[int] = mapped_column(Integer, default=0)
	status: Mapped[str] = mapped_column(String(16), default="draft")
	created_at_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	updated_at_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
	community_name: Mapped[Optional[str]] = mapped_column(String(120))
	community_link: Mapped[Optional[str]] = mapped_column(Text)
	is_generated_by_ai: Mapped[bool] = mapped_column(Boolean, default=False)
	dedupe_key: Mapped[Optional[str]] = mapped_column(String(64), index=True)


class Moment(Base):
	__tablename__ = "moments"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
	template: Mapped[Optional[str]] = mapped_column(String(64))
	text: Mapped[Optional[str]] = mapped_column(String(200))
	location_url: Mapped[Optional[str]] = mapped_column(Text)
	lat: Mapped[Optional[float]] = mapped_column(Float)
	lng: Mapped[Optional[float]] = mapped_column(Float)
	created_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	expires_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True))
	status: Mapped[str] = mapped_column(String(16), default="open")
	event_tz: Mapped[Optional[str]] = mapped_column(String(64))
	participants_ids: Mapped[Optional[str]] = mapped_column(Text)


class Report(Base):
	__tablename__ = "reports"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	target_user_id: Mapped[int] = mapped_column(BigInteger)
	from_user_id: Mapped[int] = mapped_column(BigInteger)
	context_type: Mapped[str] = mapped_column(String(16))
	context_id: Mapped[int] = mapped_column(Integer)
	reason: Mapped[Optional[str]] = mapped_column(String(64))
	comment: Mapped[Optional[str]] = mapped_column(Text)
	created_at_utc: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	status: Mapped[str] = mapped_column(String(16), default="new")


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


def get_session():
	assert Session is not None
	return Session()


def _csv_to_set(csv_value: Optional[str]) -> set[int]:
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

 

