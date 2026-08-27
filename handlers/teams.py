from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

import db
import keyboards as kb
import utils

router = Router()


def _require_admin(user):
    return user and user["role"] == "admin"


@router.message(F.text == "👥 Команды")
async def list_teams(message: Message):
    user = await db.get_user(message.from_user.id)
    if not _require_admin(user):
        await message.answer("Этот раздел доступен только администратору.")
        return
    teams = await db.list_teams()
    if not teams:
        await message.answer("Команды не найдены.")
        return
    await message.answer("Команды:", reply_markup=kb.teams_list_kb(teams))


@router.callback_query(F.data == "teams:list")
async def back_to_teams(callback: CallbackQuery):
    teams = await db.list_teams()
    await callback.message.edit_text("Команды:", reply_markup=kb.teams_list_kb(teams))
    await callback.answer()


@router.callback_query(F.data.startswith("team:"))
async def open_team_card(callback: CallbackQuery):
    code = callback.data.split(":", 1)[1]
    team = await db.get_team(code)
    if not team:
        await callback.answer("Команда не найдена", show_alert=True)
        return
    drones = await db.list_drones(team_code=code)
    members = await db.list_team_members(code)

    lines = [f"👥 <b>Команда {team['code']}</b>"]
    lines.append(f"Код для входа в бот: <code>{team['code']}</code>")
    lines.append("")
    lines.append(f"<b>Состав ({len(members)})</b>")
    if members:
        for m in members:
            tag = "👑 руководитель" if m["is_leader"] else "пилот"
            lines.append(f"  • {m['full_name']} ({tag})")
    else:
        lines.append("  Пока никто не зарегистрировался с этим кодом")
    lines.append("")
    lines.append(f"<b>Дроны команды ({len(drones)})</b>")
    if drones:
        for d in drones:
            lines.append(f"  • {d['model']} — <code>{d['serial']}</code>")
    else:
        lines.append("  дронов не назначено")

    await callback.message.edit_text("\n".join(lines), reply_markup=kb.team_card_kb(code))
    await callback.answer()


@router.callback_query(F.data.startswith("assign:menu:"))
async def assign_menu(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    if not _require_admin(user):
        await callback.answer("Только для администратора", show_alert=True)
        return
    serial = callback.data.split(":", 2)[2]
    teams = await db.list_teams()
    await callback.message.edit_text(
        f"Назначить команду дрону <code>{serial}</code>:",
        reply_markup=kb.assign_team_kb(serial, teams),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("assign:set:"))
async def assign_set(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    if not _require_admin(user):
        await callback.answer("Только для администратора", show_alert=True)
        return
    _, _, serial, team_code = callback.data.split(":")
    await db.assign_drone_team(serial, team_code)
    await callback.message.edit_text(
        f"✅ Дрон <code>{serial}</code> назначен команде {team_code}.",
        reply_markup=kb.team_card_kb(team_code),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("assign:unset:"))
async def assign_unset(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    if not _require_admin(user):
        await callback.answer("Только для администратора", show_alert=True)
        return
    serial = callback.data.split(":", 2)[2]
    await db.unassign_drone_team(serial)
    await callback.message.edit_text(f"Команда снята с дрона {serial}.")
    await callback.answer()


@router.message(F.text == "📊 Свод")
async def fleet_summary(message: Message):
    user = await db.get_user(message.from_user.id)
    if not _require_admin(user):
        await message.answer("Этот раздел доступен только администратору.")
        return

    s = await db.fleet_summary()
    lines = ["📊 <b>Свод по парку</b>", ""]
    lines.append(f"Всего дронов: {s['drones_count']}")
    for row in s["by_model"]:
        lines.append(f"  • {row['model']}: {row['c']} шт.")
    lines.append("")

    bat_replace = []
    bat_soon = []
    for b in s["batteries"]:
        status, remaining = utils.battery_status(b["cycles"], b["resource_cycles"])
        if "Заменить" in status:
            bat_replace.append(b)
        elif "Скоро" in status:
            bat_soon.append(b)
    lines.append(f"🔋 Батарей всего: {len(s['batteries'])}")
    lines.append(f"  🔴 Требуют замены: {len(bat_replace)}")
    lines.append(f"  🟡 Скоро замена: {len(bat_soon)}")
    lines.append("")

    gen_due = []
    gen_soon = []
    for g in s["generators"]:
        status, _ = utils.generator_oil_status(
            g["work_hours"], g["oil_change_interval_hours"], g["last_oil_change_hours"]
        )
        if "Пора" in status:
            gen_due.append(g)
        elif "Скоро" in status:
            gen_soon.append(g)
    lines.append(f"⚡ Генераторов в парке: {len(s['generators'])}")
    lines.append(f"  🔴 Пора менять масло: {len(gen_due)}")
    lines.append(f"  🟡 Скоро замена: {len(gen_soon)}")
    lines.append("")

    veh_due = []
    veh_soon = []
    for v in s["vehicles"]:
        status, _ = utils.vehicle_oil_status(
            v["mileage_km"], v["oil_change_interval_km"], v["last_oil_change_km"]
        )
        if "Пора" in status:
            veh_due.append(v)
        elif "Скоро" in status:
            veh_soon.append(v)
    lines.append(f"🚗 Автомобилей в парке: {len(s['vehicles'])}")
    lines.append(f"  🔴 Пора менять масло: {len(veh_due)}")
    lines.append(f"  🟡 Скоро замена: {len(veh_soon)}")

    if bat_replace or gen_due or veh_due:
        lines.append("")
        lines.append("⚠️ <b>Требуют внимания сейчас:</b>")
        for b in bat_replace:
            lines.append(f"  • Батарея {b['serial']} (дрон {b['drone_serial']})")
        for g in gen_due:
            lines.append(f"  • Генератор {g['serial']} (дрон {g['drone_serial']})")
        for v in veh_due:
            lines.append(f"  • Авто {v['plate_number']} (дрон {v['drone_serial']})")

    await message.answer("\n".join(lines))
