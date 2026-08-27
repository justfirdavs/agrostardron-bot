"""After each work day, the team must fully rinse the drone, film it, and
send the video here. The evening reminder and the 10:00 digest to
managers/admin live in scheduler.py; this module only handles collecting
today's video from a team member."""
from datetime import datetime, timedelta, timezone

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import db
import keyboards as kb
from states import WashReport

router = Router()

TASHKENT_TZ = timezone(timedelta(hours=5))


def _today_local():
    return datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d")


@router.message(F.text == "🚿 Промывка дрона")
async def start_wash(message: Message, state: FSMContext):
    user = await db.get_user(message.from_user.id)
    if not user or user["role"] not in ("leader", "pilot") or not user["team_code"]:
        await message.answer("Этот раздел доступен участникам команды, привязанным к дрону.")
        return

    today = _today_local()
    existing = await db.get_wash_reports_for_team_date(user["team_code"], today)
    if existing:
        await message.answer("✅ Видео промывки дрона за сегодня уже отправлено. Спасибо!")
        return

    await state.set_state(WashReport.waiting_video)
    await message.answer(
        "🚿 Снимите на видео полную промывку дрона и отправьте видео сюда одним сообщением.",
        reply_markup=kb.cancel_kb(),
    )


@router.message(WashReport.waiting_video, F.video)
async def receive_wash_video(message: Message, state: FSMContext, bot: Bot):
    user = await db.get_user(message.from_user.id)
    today = _today_local()

    # Guard against a double-submit race (e.g. two team members send at once).
    already = await db.get_wash_reports_for_team_date(user["team_code"], today)
    if already:
        await state.clear()
        await message.answer("✅ Видео промывки дрона за сегодня уже было получено. Спасибо!")
        return

    drone_serial = await db.get_team_drone_serial(user["team_code"]) or user["team_code"]
    await db.create_wash_report(
        team_code=user["team_code"],
        drone_serial=drone_serial,
        telegram_id=message.from_user.id,
        video_file_id=message.video.file_id,
        wash_date=today,
    )
    await state.clear()
    await message.answer("✅ Видео промывки получено. Спасибо!")


@router.message(WashReport.waiting_video)
async def wash_wrong_type(message: Message):
    if (message.text or "").strip() == "❌ Отмена":
        return  # handled by the global cancel handler in start.py
    await message.answer("Нужно именно видео. Прикрепите видеофайл промывки дрона.")
