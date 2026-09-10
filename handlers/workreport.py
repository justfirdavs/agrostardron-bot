"""Any member of a team (leader or pilot) can submit a report of the day's
work — district/region, time range, rate (л/га), area (Га), plus an
optional free-text comment. A team may send several reports in one day;
the 10:00 morning digest (scheduler.py) picks the one with the largest
area as the team's result for that day."""
from datetime import datetime, timedelta, timezone

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import db
import keyboards as kb
import utils
from states import WorkReport
from handlers.common import send_main_menu

router = Router()

TASHKENT_TZ = timezone(timedelta(hours=5))


def _today_local():
    return datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d")


def _skip_comment_kb():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Пропустить (без комментария)", callback_data="workreport:skip_comment")
    )
    return builder.as_markup()


def _parse_number(text):
    raw = (text or "").strip().replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


@router.message(F.text == "🌾 Отчёт о работе")
async def start_work_report(message: Message, state: FSMContext):
    user = await db.get_user(message.from_user.id)
    if not user or user["role"] not in ("leader", "pilot") or not user["team_code"]:
        await message.answer("Этот раздел доступен участникам команды, привязанным к дрону.")
        return
    await state.set_state(WorkReport.entering_location)
    await message.answer(
        "🌾 Отчёт о проделанной работе.\n\n"
        "Можно отправлять несколько отчётов за день — например, если меняли локацию. "
        "Утром лучший результат за вчера увидят менеджеры и админ.\n\n"
        "1/4. Укажите область и район, например: Ферганская область, Учкуприкский район",
        reply_markup=kb.cancel_kb(),
    )


@router.message(WorkReport.entering_location)
async def wr_location(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("Введите область/район текстом.")
        return
    await state.update_data(location=text)
    await state.set_state(WorkReport.entering_time_range)
    await message.answer("2/4. Укажите время работы, например: 10:00-19:30")


@router.message(WorkReport.entering_time_range)
async def wr_time_range(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("Введите время текстом, например: 10:00-19:30")
        return
    await state.update_data(time_range=text)
    await state.set_state(WorkReport.entering_rate)
    await message.answer("3/4. Укажите расход, л/га, например: 25")


@router.message(WorkReport.entering_rate)
async def wr_rate(message: Message, state: FSMContext):
    value = _parse_number(message.text)
    if value is None:
        await message.answer("Нужно число, например: 25")
        return
    await state.update_data(rate_l_ha=value)
    await state.set_state(WorkReport.entering_area)
    await message.answer("4/4. Укажите обработанную площадь, Га, например: 62.3")


@router.message(WorkReport.entering_area)
async def wr_area(message: Message, state: FSMContext):
    value = _parse_number(message.text)
    if value is None:
        await message.answer("Нужно число, например: 62.3")
        return
    await state.update_data(area_ha=value)
    await state.set_state(WorkReport.entering_comment)
    await message.answer(
        "Если нужно — допишите комментарий (например, про смену локации или ожидание "
        "фермера). Если не нужно — нажмите «Пропустить».",
        reply_markup=_skip_comment_kb(),
    )


async def _save_and_confirm(reply_target, telegram_id, state: FSMContext, comment):
    """reply_target: a Message (or callback.message) to `.answer()` on."""
    data = await state.get_data()
    user = await db.get_user(telegram_id)
    drone_serial = await db.get_team_drone_serial(user["team_code"]) or user["team_code"]
    report_id = await db.create_work_report(
        team_code=user["team_code"],
        drone_serial=drone_serial,
        telegram_id=telegram_id,
        report_date=_today_local(),
        location=data["location"],
        time_range=data["time_range"],
        rate_l_ha=data["rate_l_ha"],
        area_ha=data["area_ha"],
        comment=comment,
    )
    await state.clear()
    report = await db.get_work_report(report_id)
    preview = utils.format_work_report(report)
    await reply_target.answer(f"✅ Отчёт сохранён:\n\n{preview}")
    await send_main_menu(reply_target, user, state)


@router.message(WorkReport.entering_comment)
async def wr_comment(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    await _save_and_confirm(message, message.from_user.id, state, text or None)


@router.callback_query(F.data == "workreport:skip_comment")
async def wr_skip_comment(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup()
    await callback.answer()
    await _save_and_confirm(callback.message, callback.from_user.id, state, None)
