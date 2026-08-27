from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

import db
import keyboards as kb
from states import UpdateFlow

router = Router()

PROMPTS = {
    "flighthours": "Введите новый общий налёт дрона (в часах), например: 400.5",
    "flightcount": "Введите новое количество полётов дрона, например: 3900",
    "genhours": "Введите текущие моточасы генератора, например: 460",
    "genoil": "Подтвердите замену масла генератора — введите текущие моточасы, на которых сделана замена, например: 460",
    "vehkm": "Введите текущий пробег автомобиля (км), например: 40200",
    "vehoil": "Подтвердите замену масла в авто — введите текущий пробег (км), на котором сделана замена, например: 40200",
    "batcycles": "Введите новое количество циклов батареи, например: 700",
}


async def _is_admin(telegram_id):
    user = await db.get_user(telegram_id)
    return user and user["role"] == "admin"


@router.callback_query(F.data.startswith("upd:menu:"))
async def open_update_menu(callback: CallbackQuery):
    if not await _is_admin(callback.from_user.id):
        await callback.answer("Только для администратора", show_alert=True)
        return
    serial = callback.data.split(":", 2)[2]
    drone = await db.get_drone(serial)
    if not drone:
        await callback.answer("Дрон не найден", show_alert=True)
        return
    batteries = await db.get_batteries(serial)
    text = f"🔧 Обновление показаний\nДрон: {serial}"
    markup = kb.update_menu_kb(drone)
    await callback.message.edit_text(text, reply_markup=markup)
    if batteries:
        await callback.message.answer(
            "Обновить циклы батарей:",
            reply_markup=kb.update_battery_menu_kb(serial, batteries),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("upd:"))
async def start_update_flow(callback: CallbackQuery, state: FSMContext):
    if not await _is_admin(callback.from_user.id):
        await callback.answer("Только для администратора", show_alert=True)
        return
    parts = callback.data.split(":")
    _, kind, target = parts[0], parts[1], parts[2]
    if kind == "menu":
        return  # handled above

    prompt = PROMPTS.get(kind, "Введите новое значение:")
    await state.update_data(kind=kind, target=target)
    await state.set_state(UpdateFlow.waiting_value)
    await callback.message.answer(prompt)
    await callback.answer()


@router.message(UpdateFlow.waiting_value)
async def receive_update_value(message: Message, state: FSMContext):
    data = await state.get_data()
    kind = data.get("kind")
    target = data.get("target")

    raw = message.text.strip().replace(",", ".")
    try:
        value = float(raw)
        if value.is_integer():
            value = int(value)
    except ValueError:
        await message.answer("Нужно число. Попробуйте ещё раз, например: 123.4")
        return

    serial_for_card = None

    if kind == "flighthours":
        await db.update_drone_flight_hours(target, value)
        serial_for_card = target
        confirm = f"Налёт дрона обновлён: {value} ч"
    elif kind == "flightcount":
        await db.update_drone_flight_count(target, int(value))
        serial_for_card = target
        confirm = f"Количество полётов обновлено: {int(value)}"
    elif kind == "genhours":
        await db.update_generator_hours(target, value)
        generator = await db.get_generator(target)
        serial_for_card = generator["drone_serial"] if generator else None
        confirm = f"Моточасы генератора обновлены: {value} ч"
    elif kind == "genoil":
        await db.reset_generator_oil(target, value)
        generator = await db.get_generator(target)
        serial_for_card = generator["drone_serial"] if generator else None
        confirm = f"Замена масла генератора зафиксирована на {value} моточасах"
    elif kind == "vehkm":
        await db.update_vehicle_mileage(target, value)
        vehicle = await db.get_vehicle(target)
        serial_for_card = vehicle["drone_serial"] if vehicle else None
        confirm = f"Пробег автомобиля обновлён: {value} км"
    elif kind == "vehoil":
        await db.reset_vehicle_oil(target, value)
        vehicle = await db.get_vehicle(target)
        serial_for_card = vehicle["drone_serial"] if vehicle else None
        confirm = f"Замена масла авто зафиксирована на {value} км пробега"
    elif kind == "batcycles":
        battery = await db.get_battery(int(target))
        if not battery:
            await message.answer("Батарея не найдена.")
            await state.clear()
            return
        await db.update_battery_cycles(int(target), int(value))
        serial_for_card = battery["drone_serial"]
        confirm = f"Циклы батареи {battery['serial']} обновлены: {int(value)}"
    else:
        await message.answer("Неизвестное действие.")
        await state.clear()
        return

    await state.clear()
    await message.answer(f"✅ {confirm}")

    if serial_for_card:
        drone = await db.get_drone(serial_for_card)
        if drone:
            await message.answer(
                "Что дальше?",
                reply_markup=kb.update_menu_kb(drone),
            )
