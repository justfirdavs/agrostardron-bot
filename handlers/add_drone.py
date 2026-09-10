"""Admin-only: register a newly purchased drone into the fleet catalog.
Nothing about the self-claim flow changes — after adding a drone here, its
team leader still just types its serial number (handlers/claim.py), and
the team then adds batteries/generator/vehicle themselves as usual."""
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import db
import keyboards as kb
from states import AddDrone
from handlers.common import send_main_menu

router = Router()


def _parse_number(text):
    raw = (text or "").strip().replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


@router.message(F.text == "➕ Добавить дрон")
async def start_add_drone(message: Message, state: FSMContext):
    user = await db.get_user(message.from_user.id)
    if not user or user["role"] != "admin":
        await message.answer("Этот раздел доступен только администратору.")
        return
    await state.set_state(AddDrone.serial)
    await message.answer(
        "➕ Добавление нового дрона в парк.\n\n"
        "1/5. Введите серийный номер дрона:",
        reply_markup=kb.cancel_kb(),
    )


@router.message(AddDrone.serial)
async def ad_serial(message: Message, state: FSMContext):
    serial = (message.text or "").strip().upper()
    if not serial:
        await message.answer("Введите серийный номер текстом.")
        return
    existing = await db.get_drone(serial)
    if existing:
        await message.answer("Дрон с таким серийным номером уже есть в парке. Введите другой номер.")
        return
    await state.update_data(serial=serial)
    await state.set_state(AddDrone.manufacturer)
    await message.answer("2/5. Введите производителя, например: DJI")


@router.message(AddDrone.manufacturer)
async def ad_manufacturer(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("Введите производителя текстом.")
        return
    await state.update_data(manufacturer=text)
    await state.set_state(AddDrone.model)
    await message.answer("3/5. Введите модель дрона, например: Agras T40")


@router.message(AddDrone.model)
async def ad_model(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("Введите модель текстом.")
        return
    await state.update_data(model=text)
    await state.set_state(AddDrone.flight_hours)
    await message.answer("4/5. Введите текущий налёт (часы). Если дрон новый — отправьте 0.")


@router.message(AddDrone.flight_hours)
async def ad_flight_hours(message: Message, state: FSMContext):
    value = _parse_number(message.text)
    if value is None:
        await message.answer("Нужно число. Если дрон новый — отправьте 0.")
        return
    await state.update_data(flight_hours=value)
    await state.set_state(AddDrone.flight_count)
    await message.answer("5/5. Введите количество полётов. Если дрон новый — отправьте 0.")


@router.message(AddDrone.flight_count)
async def ad_flight_count(message: Message, state: FSMContext):
    value = _parse_number(message.text)
    if value is None:
        await message.answer("Нужно число. Если дрон новый — отправьте 0.")
        return
    data = await state.get_data()
    await db.create_drone(
        serial=data["serial"],
        manufacturer=data["manufacturer"],
        model=data["model"],
        flight_hours=data["flight_hours"],
        flight_count=int(value),
    )
    await state.clear()
    await message.answer(
        f"✅ Дрон <code>{data['serial']}</code> ({data['manufacturer']} {data['model']}) добавлен в парк.\n\n"
        f"Дальше — как обычно: руководитель команды нажимает /start (или открывает меню, "
        f"если уже зарегистрирован) и вводит этот серийный номер, чтобы закрепить дрон за "
        f"собой, после чего команда сама вносит батареи, генератор и автомобиль."
    )
    user = await db.get_user(message.from_user.id)
    await send_main_menu(message, user, state)
