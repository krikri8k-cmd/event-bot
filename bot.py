from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Location
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import load_settings
from database import init_engine, create_all, get_session, User, Event, Moment, rsvp_event
from utils.geo_utils import haversine_km, geocode_address, get_timezone, to_google_maps_link, static_map_url, local_to_utc
from ai_utils import fetch_ai_events_nearby

logging.basicConfig(level=logging.INFO)


class CreateEventFSM(StatesGroup):
	title = State()
	time_local = State()
	location = State()
	description = State()
	max_participants = State()
	preview = State()


def main_menu_kb() -> ReplyKeyboardMarkup:
	return ReplyKeyboardMarkup(
		keyboard=[
			[KeyboardButton(text="📍 Что рядом", request_location=False)],
			[KeyboardButton(text="➕ Создать")],
			[KeyboardButton(text="🤝 Поделиться")],
		],
		resize_keyboard=True,
	)


async def ensure_user(message: Message) -> Optional[User]:
	with get_session() as session:
		user = session.get(User, message.from_user.id)
		if not user:
			user = User(
				id=message.from_user.id,
				username=message.from_user.username,
				full_name=message.from_user.full_name,
			)
			session.add(user)
			session.commit()
		return user


def _is_admin(user_id: int) -> bool:
	return user_id in load_settings().admin_ids


async def cmd_start(message: Message, state: FSMContext):
	await ensure_user(message)
	await message.answer(
		"Привет! Я EventAroundBot. Помогаю находить события рядом и создавать свои.",
		reply_markup=main_menu_kb(),
	)


async def ask_location(message: Message):
	kb = ReplyKeyboardMarkup(
		keyboard=[[KeyboardButton(text="📍 Отправить геопозицию", request_location=True)]],
		resize_keyboard=True,
		one_time_keyboard=True,
	)
	await message.answer("Отправь свежую геопозицию, чтобы я нашла события рядом ✨", reply_markup=kb)


async def on_what_nearby(message: Message):
	await ask_location(message)


async def on_location(message: Message):
	if not message.location:
		await ask_location(message)
		return
	lat = message.location.latitude
	lng = message.location.longitude

	settings = load_settings()
	await message.answer("Смотрю, что рядом…", reply_markup=ReplyKeyboardRemove())

	with get_session() as session:
		user = session.get(User, message.from_user.id)
		if not user:
			user = User(id=message.from_user.id, username=message.from_user.username, full_name=message.from_user.full_name)
			session.add(user)
		user.last_lat = lat
		user.last_lng = lng
		user.last_geo_at_utc = datetime.utcnow()
		session.commit()

	# Fetch AI suggestions in background (best-effort)
	ai_items = await fetch_ai_events_nearby(lat, lng)

	# Persist AI items with dedupe, compute UTC
	with get_session() as session:
		for it in ai_items:
			tz = await get_timezone(it["lat"], it["lng"]) or "UTC"
			utc_dt = local_to_utc(it.get("time_local") or "", tz)
			dedupe_key = f"{it['title']}|{utc_dt.isoformat() if utc_dt else ''}|{it['lat']:.6f}|{it['lng']:.6f}"

			exists = session.execute(
				__import__("sqlalchemy").select(Event).where(Event.dedupe_key == dedupe_key)
			)
			if exists.scalars().first():
				continue
			ev = Event(
				title=it["title"],
				description=it.get("description") or None,
				time_local=it.get("time_local") or None,
				event_tz=tz,
				time_utc=utc_dt,
				location_name=it.get("location_name") or None,
				location_url=it.get("location_url") or None,
				lat=it["lat"],
				lng=it["lng"],
				organizer_id=message.from_user.id,
				organizer_username=message.from_user.username,
				status="open",
				is_generated_by_ai=True,
				community_name=it.get("community_name") or None,
				community_link=it.get("community_link") or None,
				dedupe_key=dedupe_key,
			)
			session.add(ev)
		session.commit()

	# Query nearby from DB
	items = []
	with get_session() as session:
		res = session.execute(__import__("sqlalchemy").select(Event).where(Event.status.in_(["open", "closed"])) )
		events = res.scalars().all()
		for ev in events:
			if ev.lat is None or ev.lng is None:
				continue
			dist = haversine_km(lat, lng, ev.lat, ev.lng)
			items.append((ev, dist))

	if not items:
		await message.answer("Пока ничего не нашла. Попробуй позже или создай своё событие через ‘➕ Создать’.", reply_markup=main_menu_kb())
		return

	items.sort(key=lambda x: x[1])

	lines = []
	for ev, dist in items:
		url = ev.location_url or to_google_maps_link(ev.lat, ev.lng)
		time_part = f" — {ev.time_local} ({ev.event_tz})" if ev.time_local and ev.event_tz else ""
		lines.append(f"{ev.title}{time_part}\n{dist:.1f} км\n{url}")
	text = "\n\n".join(lines)

	# Static map
	points = []
	label_ord = ord("A")
	for ev, _ in items[:10]:
		points.append((chr(label_ord), ev.lat, ev.lng))
		label_ord += 1
	map_url = static_map_url(lat, lng, points) or ""

	if map_url:
		await message.answer_photo(map_url, caption=text, reply_markup=main_menu_kb())
	else:
		await message.answer(text, reply_markup=main_menu_kb())


async def on_share(message: Message):
	bot: Bot = message.bot
	me = await bot.get_me()
	bot_username = me.username
	text = (
		"Прикрепи бота в чат — чтобы всем было удобнее искать активности вместе.\n\n"
		f"Добавить: t.me/{bot_username}?startgroup=true\n"
		f"Личная ссылка: t.me/{bot_username}\n\n"
		"Можешь делиться конкретным событием, когда откроешь его карточку — я пришлю deep-link."
	)
	await message.answer(text, reply_markup=main_menu_kb())


async def cmd_forget_location(message: Message):
	with get_session() as session:
		user = session.get(User, message.from_user.id)
		if user:
			user.last_lat = None
			user.last_lng = None
			user.last_geo_at_utc = None
			session.commit()
	await message.answer("Ок, забыла твою последнюю геолокацию. Когда понадобится — запросим заново.", reply_markup=main_menu_kb())


# FSM: Create Event minimal flow

async def on_create(message: Message, state: FSMContext):
	await state.set_state(CreateEventFSM.title)
	await message.answer("Название события? (до 120 символов)")


async def fsm_title(message: Message, state: FSMContext):
	title = message.text.strip()
	if len(title) < 3 or len(title) > 120:
		await message.answer("Пожалуйста, от 3 до 120 символов.")
		return
	await state.update_data(title=title)
	await state.set_state(CreateEventFSM.time_local)
	await message.answer("Время (локальное) в формате YYYY-MM-DD HH:MM")


async def fsm_time_local(message: Message, state: FSMContext):
	time_local = message.text.strip()
	if len(time_local) != 16 or time_local[4] != '-' or time_local[7] != '-' or time_local[10] != ' ':
		await message.answer("Формат: YYYY-MM-DD HH:MM")
		return
	await state.update_data(time_local=time_local)
	await state.set_state(CreateEventFSM.location)
	await message.answer("Место: отправь адрес или ссылку Google Maps, либо геометку.")


async def fsm_location(message: Message, state: FSMContext):
	data = await state.get_data()
	user_input = message.text or ""
	lat = None
	lng = None
	location_name = None
	location_url = None

	if message.location:
		lat = message.location.latitude
		lng = message.location.longitude
	else:
		# try parse lat,lng in text
		import re
		m = re.search(r"([-+]?\d+\.\d+),\s*([-+]?\d+\.\d+)", user_input)
		if m:
			lat = float(m.group(1))
			lng = float(m.group(2))
		else:
			# try geocode address
			coords = await geocode_address(user_input)
			if coords:
				lat, lng = coords
				location_name = user_input[:255]
	if not (lat and lng):
		await message.answer("Не удалось распознать место. Отправь геометку или адрес.")
		return

	tz = await get_timezone(lat, lng) or "UTC"
	await state.update_data(lat=lat, lng=lng, event_tz=tz, location_name=location_name, location_url=location_url)
	await state.set_state(CreateEventFSM.description)
	await message.answer("Короткое описание (опционально, до 500 символов). Отправь текст или '-' чтобы пропустить.")


async def fsm_description(message: Message, state: FSMContext):
	text = message.text or ""
	description = None if text.strip() == "-" else text.strip()[:500]
	await state.update_data(description=description)
	await state.set_state(CreateEventFSM.max_participants)
	await message.answer("Лимит участников (число, 0 или пусто — без лимита).")


async def fsm_max(message: Message, state: FSMContext):
	value = message.text.strip()
	try:
		max_p = int(value)
		if max_p < 0:
			raise ValueError
	except Exception:
		max_p = 0
	await state.update_data(max_participants=max_p)

	data = await state.get_data()
	title = data.get("title")
	time_local = data.get("time_local")
	lat = data.get("lat")
	lng = data.get("lng")
	tz = data.get("event_tz")
	desc = data.get("description")

	preview = f"Предпросмотр:\n{title}\n{time_local} ({tz})\n{lat:.6f},{lng:.6f}\n{desc or ''}\nОпубликовать?".strip()
	kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Опубликовать", callback_data="publish_event")]])
	await state.set_state(CreateEventFSM.preview)
	await message.answer(preview, reply_markup=kb)


async def publish_event(cb: CallbackQuery, state: FSMContext):
	data = await state.get_data()
	user_id = cb.from_user.id

	with get_session() as session:
		ev = Event(
			title=data.get("title"),
			description=data.get("description"),
			time_local=data.get("time_local"),
			event_tz=data.get("event_tz"),
			time_utc=local_to_utc(data.get("time_local"), data.get("event_tz")) if (data.get("time_local") and data.get("event_tz")) else None,
			location_name=data.get("location_name"),
			location_url=data.get("location_url"),
			lat=data.get("lat"),
			lng=data.get("lng"),
			organizer_id=user_id,
			organizer_username=cb.from_user.username,
			max_participants=data.get("max_participants") or 0,
			status="open",
		)
		session.add(ev)
		session.commit()

	await state.clear()
	await cb.message.edit_text("Событие опубликовано!", reply_markup=None)


# Admin commands (minimal)

async def cmd_admin(message: Message):
	if not _is_admin(message.from_user.id):
		return
	text = (
		"Админ-меню:\n"
		"/publish <id> — открыть регистрацию\n"
		"/close <id> — закрыть регистрацию\n"
		"/delete <id> — удалить событие\n"
		"/import_csv — пришли CSV (текстом), формат: Title;LocationURL;LocationName;TimeLocal;MaxParticipants;Description;CommunityName;CommunityLink"
	)
	await message.answer(text)


async def _admin_change_status(message: Message, status: str):
	if not _is_admin(message.from_user.id):
		return
	parts = (message.text or "").split()
	if len(parts) < 2 or not parts[1].isdigit():
		await message.answer("Укажи ID: /publish 123")
		return
	event_id = int(parts[1])
	with get_session() as session:
		ev = session.get(Event, event_id)
		if not ev:
			await message.answer("Не нашла событие")
			return
		if status == "delete":
			session.delete(ev)
		else:
			ev.status = status
		session.commit()
	await message.answer("Готово")


async def cmd_publish(message: Message):
	await _admin_change_status(message, "open")


async def cmd_close(message: Message):
	await _admin_change_status(message, "closed")


async def cmd_delete(message: Message):
	await _admin_change_status(message, "delete")


async def cmd_import_csv(message: Message):
	if not _is_admin(message.from_user.id):
		return
	text = message.text or ""
	# Allow sending CSV right after command as a new message; here expect it's this one
	lines = [l for l in text.splitlines() if ";" in l]
	if len(lines) <= 1:
		await message.answer("Пришли CSV текстом в этом сообщении сразу после команды. Первая строка — заголовок.")
		return
	header = lines[0]
	created = 0
	skipped = 0
	for row in lines[1:]:
		try:
			Title, LocationURL, LocationName, TimeLocal, MaxParticipants, Description, CommunityName, CommunityLink = (
				(row.split(";") + [""] * 8)[:8]
			)
			lat = None
			lng = None
			if LocationURL:
				# try parse coords from URL
				import re
				m = re.search(r"@(\-?\d+\.\d+),(\-?\d+\.\d+)", LocationURL)
				if m:
					lat = float(m.group(1))
					lng = float(m.group(2))
			if lat is None or lng is None:
				if LocationName:
					coords = await geocode_address(LocationName)
					if coords:
						lat, lng = coords
			if lat is None or lng is None:
				skipped += 1
				continue
			tz = await get_timezone(lat, lng) or "UTC"
			utc_dt = local_to_utc(TimeLocal, tz)
			dedupe_key = f"{Title}|{utc_dt.isoformat() if utc_dt else ''}|{lat:.6f}|{lng:.6f}"

			with get_session() as session:
				exists = session.execute(__import__("sqlalchemy").select(Event).where(Event.dedupe_key == dedupe_key))
				if exists.scalars().first():
					skipped += 1
					continue
				ev = Event(
					title=Title[:120],
					description=(Description or None),
					time_local=TimeLocal[:16] or None,
					event_tz=tz,
					time_utc=utc_dt,
					location_name=(LocationName or None),
					location_url=(LocationURL or None),
					lat=lat,
					lng=lng,
					organizer_id=message.from_user.id,
					organizer_username=message.from_user.username,
					max_participants=int(MaxParticipants) if MaxParticipants.isdigit() else 0,
					status="draft",
					community_name=(CommunityName or None),
					community_link=(CommunityLink or None),
					dedupe_key=dedupe_key,
				)
				session.add(ev)
				session.commit()
				created += 1
		except Exception:
			skipped += 1
			continue
	await message.answer(f"Импорт завершён: ok={created}, skipped={skipped}")


async def setup_scheduler(dp: Dispatcher):
	scheduler = AsyncIOScheduler(timezone="UTC")
	# Periodic jobs
	async def tick_events_done():
		with get_session() as session:
			now = datetime.utcnow()
			res = session.execute(__import__("sqlalchemy").select(Event).where(Event.status.in_(["open", "closed"])) )
			for ev in res.scalars().all():
				if ev.time_utc and ev.time_utc <= now:
					ev.status = "done"
			session.commit()

	async def tick_moments_expire():
		with get_session() as session:
			now = datetime.utcnow()
			res = session.execute(__import__("sqlalchemy").select(Moment).where(Moment.status == "open"))
			for m in res.scalars().all():
				if m.expires_utc and m.expires_utc <= now:
					m.status = "expired"
			session.commit()

	loop = asyncio.get_running_loop()
	scheduler.add_job(lambda: loop.create_task(tick_events_done()), "interval", minutes=1)
	scheduler.add_job(lambda: loop.create_task(tick_moments_expire()), "interval", minutes=1)
	scheduler.start()
	dp['scheduler'] = scheduler


async def on_startup(bot: Bot, dp: Dispatcher):
	settings = load_settings()
	# Require DB to be available; init_engine will raise on failure
	init_engine(settings.database_url)
	create_all()
	await setup_scheduler(dp)


def make_dispatcher() -> Dispatcher:
	dp = Dispatcher()
	dp.message.register(cmd_start, CommandStart())
	dp.message.register(on_what_nearby, F.text == "📍 Что рядом")
	dp.message.register(on_create, F.text == "➕ Создать")
	dp.message.register(on_share, F.text == "🤝 Поделиться")
	dp.message.register(on_location, F.location)
	dp.message.register(cmd_forget_location, Command("forget_location"))
	dp.message.register(cmd_admin, Command("admin"))
	dp.message.register(cmd_publish, Command("publish"))
	dp.message.register(cmd_close, Command("close"))
	dp.message.register(cmd_delete, Command("delete"))
	dp.message.register(cmd_import_csv, Command("import_csv"))

	dp.message.register(fsm_title, CreateEventFSM.title)
	dp.message.register(fsm_time_local, CreateEventFSM.time_local)
	dp.message.register(fsm_location, CreateEventFSM.location)
	dp.message.register(fsm_description, CreateEventFSM.description)
	dp.message.register(fsm_max, CreateEventFSM.max_participants)
	dp.callback_query.register(publish_event, F.data == "publish_event")
	return dp


async def run() -> None:
	settings = load_settings()
	bot = Bot(token=settings.telegram_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
	dp = make_dispatcher()
	await on_startup(bot, dp)
	await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
	asyncio.run(run())


