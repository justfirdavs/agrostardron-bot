"""Team-leader wizard for entering the real generator / battery / vehicle
data for their drone (replaces the placeholder values from the original
spreadsheet)."""
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

import db
from states import EquipmentSetup

router = Router()


def _drone_pick_kb(drones):
    builder = InlineKeyboardBuilder()
    for d in drones:
        builder.row(
            InlineKeyboardButton(
                text=f"{d['model']} · {d['serial']}", callback_data=f"equip:start:{d['serial']}"
            )
        )
    return builder.as_markup()


async def maybe_start_wizard(message: Message, state: FSMContext, team_code: str):
    """Called right after a team leader registers. Kicks off the wizard if
    there's exactly one drone to fill in, offers a choice if there are
    several, or explains that nothing is assigned yet."""
    drones = await db.list_drones(team_code=team_code)
    if not drones:
        await message.answer(
            "Пока к вашей команде не привязан ни один дрон. Как только "
            "администратор назначит дрон вашей команде, зайдите в «⚙️ Данные "
            "дрона», чтобы внести серийные номера генератора, батарей и авто."
        )
        return

    missing = await db.list_drones_missing_equipment(team_code)
    if not missing:
        return

    if len(missing) == 1:
        await start_wizard(message, state, missing[0]["serial"])
        return

    await message.answer(
        "По вашим дронам ещё не внесены данные генератора/батарей/авто. "
        "Выберите дрон, с которого начнём:",
        reply_markup=_drone_pick_kb(missing),
    )


async def start_wizard(message: Message, state: FSMContext, drone_serial: str):
    await state.update_data(drone_serial=drone_serial, batteries=[])
    await state.set_state(EquipmentSetup.generator_serial)
    await message.answer(
        f"🚁 Дрон <code>{drone_serial}</code>\n\n"
        f"1/5. Введите серийный номер <b>генератора</b>:"
    )


@router.message(F.text == "⚙️ Данные дрона")
async def equipment_menu(message: Message, state: FSMContext):
    user = await db.get_user(message.from_user.id)
    if not user or not user["is_leader"]:
        await message.answer("Этот раздел доступен только руководителю команды.")
        return
    drones = await db.list_drones(team_code=user["team_code"])
    if not drones:
        await message.answer("Пока к вашей команде не привязан ни один дрон.")
        return
    if len(drones) == 1:
        await start_wizard(message, state, drones[0]["serial"])
        return
    await message.answer("Выберите дрон:", reply_markup=_drone_pick_kb(drones))


@router.callback_query(F.data.startswith("equip:start:"))
async def equip_pick_drone(callback: CallbackQuery, state: FSMContext):
    serial = callback.data.split(":", 2)[2]
    if not await db.is_leader_of_drone(callback.from_user.id, serial):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_reply_markup()
    await start_wizard(callback.message, state, serial)
    await callback.answer()


# ---------------- generator ----------------

@router.message(EquipmentSetup.generator_serial)
async def gen_serial(message: Message, state: FSMContext):
    await state.update_data(gen_serial=message.text.strip())
    await state.set_state(EquipmentSetup.generator_hours)
    await message.answer("2/5. Введите текущие моточасы генератора (число), например: 120")


@router.message(EquipmentSetup.generator_hours)
async def gen_hours(message: Message, state: FSMContext):
    value = _parse_number(message.text)
    if value is None:
        await message.answer("Нужно число. Например: 120")
        return
    await state.update_data(gen_hours=value)
    await state.set_state(EquipmentSetup.generator_last_oil_hours)
    await message.answer(
        "На каких моточасах в последний раз меняли масло в генераторе?\n"
        "Если ни разу не меняли — отправьте 0."
    )


@router.message(EquipmentSetup.generator_last_oil_hours)
async def gen_last_oil(message: Message, state: FSMContext):
    value = _parse_number(message.text)
    if value is None:
        await message.answer("Нужно число. Если не меняли — отправьте 0.")
        return
    await state.update_data(gen_last_oil=value)
    await state.set_state(EquipmentSetup.battery1_serial)
    await message.answer("3/5. Батарея 1 — введите серийный номер:")


# ---------------- batteries ----------------

BATTERY_STEPS = [
    (EquipmentSetup.battery1_serial, EquipmentSetup.battery1_cycles, 1),
    (EquipmentSetup.battery2_serial, EquipmentSetup.battery2_cycles, 2),
    (EquipmentSetup.battery3_serial, EquipmentSetup.battery3_cycles, 3),
]


@router.message(EquipmentSetup.battery1_serial)
async def bat1_serial(message: Message, state: FSMContext):
    await state.update_data(bat1_serial=message.text.strip())
    await state.set_state(EquipmentSetup.battery1_cycles)
    await message.answer("Батарея 1 — введите количество циклов:")


@router.message(EquipmentSetup.battery1_cycles)
async def bat1_cycles(message: Message, state: FSMContext):
    value = _parse_number(message.text)
    if value is None:
        await message.answer("Нужно число, например: 150")
        return
    await state.update_data(bat1_cycles=int(value))
    await state.set_state(EquipmentSetup.battery2_serial)
    await message.answer("Батарея 2 — введите серийный номер:")


@router.message(EquipmentSetup.battery2_serial)
async def bat2_serial(message: Message, state: FSMContext):
    await state.update_data(bat2_serial=message.text.strip())
    await state.set_state(EquipmentSetup.battery2_cycles)
    await message.answer("Батарея 2 — введите количество циклов:")


@router.message(EquipmentSetup.battery2_cycles)
async def bat2_cycles(message: Message, state: FSMContext):
    value = _parse_number(message.text)
    if value is None:
        await message.answer("Нужно число, например: 150")
        return
    await state.update_data(bat2_cycles=int(value))
    await state.set_state(EquipmentSetup.battery3_serial)
    await message.answer("Батарея 3 — введите серийный номер:")


@router.message(EquipmentSetup.battery3_serial)
async def bat3_serial(message: Message, state: FSMContext):
    await state.update_data(bat3_serial=message.text.strip())
    await state.set_state(EquipmentSetup.battery3_cycles)
    await message.answer("Батарея 3 — введите количество циклов:")


@router.message(EquipmentSetup.battery3_cycles)
async def bat3_cycles(message: Message, state: FSMContext):
    value = _parse_number(message.text)
    if value is None:
        await message.answer("Нужно число, например: 150")
        return
    await state.update_data(bat3_cycles=int(value))
    await state.set_state(EquipmentSetup.vehicle_manufacturer)
    await message.answer("4/5. Автомобиль — введите производителя (марку), например: Changan")


# ---------------- vehicle ----------------

@router.message(EquipmentSetup.vehicle_manufacturer)
async def veh_manufacturer(message: Message, state: FSMContext):
    await state.update_data(veh_manufacturer=message.text.strip())
    await state.set_state(EquipmentSetup.vehicle_plate)
    await message.answer("Введите гос. номер автомобиля:")


@router.message(EquipmentSetup.vehicle_plate)
async def veh_plate(message: Message, state: FSMContext):
    await state.update_data(veh_plate=message.text.strip())
    await state.set_state(EquipmentSetup.vehicle_vin)
    await message.answer("Введите VIN автомобиля (если не знаете — отправьте «-»):")


@router.message(EquipmentSetup.vehicle_vin)
async def veh_vin(message: Message, state: FSMContext):
    text = message.text.strip()
    await state.update_data(veh_vin=None if text == "-" else text)
    await state.set_state(EquipmentSetup.vehicle_mileage)
    await message.answer("5/5. Введите текущий пробег автомобиля (км):")


@router.message(EquipmentSetup.vehicle_mileage)
async def veh_mileage(message: Message, state: FSMContext):
    value = _parse_number(message.text)
    if value is None:
        await message.answer("Нужно число, например: 40200")
        return
    await state.update_data(veh_mileage=value)
    await state.set_state(EquipmentSetup.vehicle_last_oil_km)
    await message.answer(
        "На каком пробеге в последний раз меняли масло в авто?\n"
        "Если ни разу не меняли — отправьте 0."
    )


@router.message(EquipmentSetup.vehicle_last_oil_km)
async def veh_last_oil(message: Message, state: FSMContext):
    value = _parse_number(message.text)
    if value is None:
        await message.answer("Нужно число. Если не меняли — отправьте 0.")
        return

    data = await state.get_data()
    drone_serial = data["drone_serial"]

    await db.set_drone_generator(
        drone_serial, data["gen_serial"], data["gen_hours"], data["gen_last_oil"]
    )
    await db.replace_batteries_for_drone(
        drone_serial,
        [
            (data["bat1_serial"], data["bat1_cycles"]),
            (data["bat2_serial"], data["bat2_cycles"]),
            (data["bat3_serial"], data["bat3_cycles"]),
        ],
    )
    await db.set_drone_vehicle(
        drone_serial,
        data["veh_manufacturer"],
        data["veh_plate"],
        data["veh_vin"],
        data["veh_mileage"],
        value,
    )

    await state.clear()
    await message.answer(f"✅ Данные по дрону {drone_serial} сохранены. Спасибо!")

    user = await db.get_user(message.from_user.id)
    remaining = await db.list_drones_missing_equipment(user["team_code"])
    if remaining:
        await message.answer(
            f"У вашей команды есть ещё дрон(ы) без данных ({len(remaining)}). "
            f"Открыть «⚙️ Данные дрона», чтобы продолжить."
        )


def _parse_number(text):
    raw = (text or "").strip().replace(",", ".")
    try:
        value = float(raw)
    except ValueError:
        return None
    if value.is_integer():
        return int(value)
    return value
