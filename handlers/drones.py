from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

import db
import keyboards as kb
from handlers.common import format_drone_card

router = Router()


async def _drones_for_user(user):
    if user["role"] == "admin":
        return await db.list_drones()
    return await db.list_drones(team_code=user["team_code"])


@router.message(F.text.in_({"🚁 Дроны", "🚁 Мои дроны"}))
async def list_drones(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("Нажмите /start")
        return
    drones = await _drones_for_user(user)
    if not drones:
        await message.answer("Дроны не найдены.")
        return
    title = "Весь парк дронов:" if user["role"] == "admin" else "Дроны вашей команды:"
    await message.answer(title, reply_markup=kb.drones_list_kb(drones, page=0))


@router.callback_query(F.data.startswith("drones_page:"))
async def paginate_drones(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    page = int(callback.data.split(":")[1])
    drones = await _drones_for_user(user)
    try:
        await callback.message.edit_text(
            "Весь парк дронов:" if user["role"] == "admin" else "Дроны вашей команды:",
            reply_markup=kb.drones_list_kb(drones, page=page),
        )
    except Exception:
        await callback.message.answer(
            "Весь парк дронов:" if user["role"] == "admin" else "Дроны вашей команды:",
            reply_markup=kb.drones_list_kb(drones, page=page),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("drone:"))
async def open_drone_card(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    serial = callback.data.split(":", 1)[1]

    drone = await db.get_drone(serial)
    if not drone:
        await callback.answer("Дрон не найден", show_alert=True)
        return

    if user["role"] != "admin" and drone["team_code"] != user["team_code"]:
        await callback.answer("Нет доступа к этому дрону", show_alert=True)
        return

    team_members = await db.list_team_members(drone["team_code"]) if drone["team_code"] else []
    batteries = await db.get_batteries(serial)
    generator = await db.get_generator(drone["generator_serial"]) if drone["generator_serial"] else None
    vehicle = await db.get_vehicle(drone["vehicle_plate"]) if drone["vehicle_plate"] else None
    repair_stats = await db.count_drone_repairs(serial)
    recent_repairs = await db.get_drone_repairs(serial, limit=3)
    gen_repair_stats = None
    if generator:
        gr = await db.get_generator_repairs(generator["serial"], limit=1)
        cur_count = generator["repairs_count"] or 0
        last_date = gr[0]["date"] if gr else None
        gen_repair_stats = {"c": cur_count, "last_date": last_date}

    text = format_drone_card(
        drone, team_members, batteries, generator, vehicle, repair_stats, gen_repair_stats, recent_repairs
    )

    is_admin = user["role"] == "admin"
    is_leader_here = bool(user["is_leader"]) and drone["team_code"] == user["team_code"]
    markup = kb.drone_card_kb(serial, is_admin=is_admin, is_leader=is_leader_here)

    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except Exception:
        await callback.message.answer(text, reply_markup=markup)
    await callback.answer()
