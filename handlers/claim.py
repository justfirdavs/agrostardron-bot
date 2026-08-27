"""Leader/pilot self-attachment to a drone by serial number.

Per the current flow: the admin no longer assigns a drone to a team. A
newly-approved leader types their drone's serial number, which becomes the
team's code (team_code == drone_serial) and immediately leads into the
equipment wizard. A pilot just types the same serial number and is
auto-attached to whatever team already claimed that drone.
"""
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import db
from states import ClaimDrone
from handlers.common import send_main_menu

router = Router()

MAX_PILOTS_PER_TEAM = 2


@router.message(ClaimDrone.leader_serial)
async def leader_claim(message: Message, state: FSMContext):
    serial = (message.text or "").strip().upper()
    if not serial:
        await message.answer("Введите серийный номер дрона текстом.")
        return

    drone = await db.get_drone(serial)
    if not drone:
        await message.answer(
            "Дрон с таким серийным номером не найден в парке. Проверьте номер "
            "(он указан на самом дроне) и попробуйте ещё раз."
        )
        return

    if drone["team_code"]:
        existing_leader = await db.get_team_leader(drone["team_code"])
        if existing_leader and existing_leader["telegram_id"] != message.from_user.id:
            await message.answer(
                "Этот дрон уже закреплён за другим руководителем. Если это ошибка — "
                "обратитесь к администратору."
            )
            return

    await db.assign_drone_team(serial, serial)
    await db.set_user_team_code(message.from_user.id, serial)
    await message.answer(f"✅ Дрон <code>{serial}</code> закреплён за вами как за руководителем команды.")

    from handlers.equipment import start_wizard
    await start_wizard(message, state, serial)


@router.message(ClaimDrone.pilot_serial)
async def pilot_claim(message: Message, state: FSMContext):
    serial = (message.text or "").strip().upper()
    if not serial:
        await message.answer("Введите серийный номер дрона текстом.")
        return

    drone = await db.get_drone(serial)
    if not drone:
        await message.answer(
            "Дрон с таким серийным номером не найден в парке. Проверьте номер "
            "(он указан на самом дроне) и попробуйте ещё раз."
        )
        return

    if not drone["team_code"]:
        await message.answer(
            "К этому дрону ещё не привязан руководитель. Сначала руководитель "
            "команды должен ввести серийный номер этого дрона, потом попробуйте снова."
        )
        return

    pilots_count = await db.count_pilots_in_team(drone["team_code"])
    if pilots_count >= MAX_PILOTS_PER_TEAM:
        await message.answer(
            f"В этой команде уже {MAX_PILOTS_PER_TEAM} пилота(ов). Если это ошибка — "
            f"обратитесь к администратору."
        )
        return

    await db.set_user_team_code(message.from_user.id, drone["team_code"])
    await state.clear()
    await message.answer(f"✅ Вы привязаны к команде дрона <code>{drone['team_code']}</code>.")

    user = await db.get_user(message.from_user.id)
    await send_main_menu(message, user, state)
