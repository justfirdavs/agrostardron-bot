from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

import db
import keyboards as kb
import utils
from states import TeamRename

router = Router()


def _require_admin(user):
    return user and user["role"] == "admin"


def _require_view(user):
    return user and user["role"] in ("admin", "manager")


@router.message(F.text == "👥 Команды")
async def list_teams(message: Message):
    user = await db.get_user(message.from_user.id)
    if not _require_view(user):
        await message.answer("Этот раздел доступен администратору и менеджерам.")
        return
    teams = await db.list_claimed_teams_with_names()
    if not teams:
        await message.answer("Пока ни одна команда не привязана к дрону.")
        return
    await message.answer("Команды:", reply_markup=kb.teams_list_kb(teams))


@router.callback_query(F.data == "teams:list")
async def back_to_teams(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    if not _require_view(user):
        await callback.answer("Нет доступа", show_alert=True)
        return
    teams = await db.list_claimed_teams_with_names()
    await callback.message.edit_text("Команды:", reply_markup=kb.teams_list_kb(teams))
    await callback.answer()


async def _render_team_card(code):
    """Builds (text, markup) for a team card. Returns (None, None) if the
    team no longer has a claimed drone (e.g. its leader was just removed)."""
    claimed = await db.list_claimed_teams()
    if code not in claimed:
        return None, None
    drones = await db.list_drones(team_code=code)
    members = await db.list_team_members(code)
    name = await db.get_team_name(code)

    title = f"👥 <b>{name}</b> (код {code})" if name else f"👥 <b>Команда {code}</b>"
    lines = [title, ""]
    lines.append(f"<b>Состав ({len(members)})</b>")
    if members:
        for m in members:
            tag = "👑 руководитель" if m["role"] == "leader" else "пилот"
            contact_bits = []
            if m["phone"]:
                contact_bits.append(m["phone"])
            if m["username"]:
                contact_bits.append(f"@{m['username']}")
            contact = " · ".join(contact_bits) if contact_bits else "контакт не указан"
            lines.append(f"  • {m['full_name']} ({tag})")
            lines.append(f"    📱 {contact}")
    else:
        lines.append("  Пока никто из команды не зарегистрирован в боте")
    lines.append("")
    lines.append(f"<b>Дроны команды ({len(drones)})</b>")
    if drones:
        for d in drones:
            lines.append(f"  • {d['model']} — <code>{d['serial']}</code>")
    else:
        lines.append("  дронов не назначено")

    return "\n".join(lines), members


@router.callback_query(F.data.startswith("team:"))
async def open_team_card(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    if not _require_view(user):
        await callback.answer("Нет доступа", show_alert=True)
        return
    code = callback.data.split(":", 1)[1]
    text, members = await _render_team_card(code)
    if text is None:
        await callback.answer("Команда не найдена", show_alert=True)
        return
    is_admin = user["role"] == "admin"
    markup = kb.team_card_kb(code, members=members, is_admin=is_admin)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("team_rename:"))
async def team_rename_start(callback: CallbackQuery, state: FSMContext):
    user = await db.get_user(callback.from_user.id)
    if not _require_admin(user):
        await callback.answer("Только для администратора", show_alert=True)
        return
    code = callback.data.split(":", 1)[1]
    await state.update_data(team_code=code)
    await state.set_state(TeamRename.waiting_name)
    await callback.message.answer(
        f"Введите новое имя для команды <code>{code}</code> (или «-», чтобы вернуть код как имя):",
        reply_markup=kb.cancel_kb(),
    )
    await callback.answer()


@router.message(TeamRename.waiting_name)
async def team_rename_finish(message: Message, state: FSMContext):
    user = await db.get_user(message.from_user.id)
    if not _require_admin(user):
        await state.clear()
        return
    data = await state.get_data()
    code = data.get("team_code")
    text = (message.text or "").strip()
    await db.set_team_name(code, None if text == "-" else text)
    await state.clear()
    await message.answer("✅ Имя команды обновлено.")

    body, members = await _render_team_card(code)
    if body:
        await message.answer(body, reply_markup=kb.team_card_kb(code, members=members, is_admin=True))


@router.callback_query(F.data.startswith("team_kick:"))
async def team_kick_member(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    if not _require_admin(user):
        await callback.answer("Только для администратора", show_alert=True)
        return
    _, telegram_id, code = callback.data.split(":")
    target = await db.get_user(int(telegram_id))
    await db.remove_team_member(int(telegram_id))
    name = target["full_name"] if target else str(telegram_id)
    await callback.answer(f"{name} удалён(а) из команды", show_alert=True)

    try:
        await callback.bot.send_message(
            int(telegram_id),
            "Вас удалили из команды. Если это ошибка — обратитесь к администратору. "
            "Нажмите /start, чтобы привязаться заново.",
        )
    except Exception:
        pass

    text, members = await _render_team_card(code)
    if text is None:
        await callback.message.edit_text(
            "Команда расформирована (был удалён руководитель). Дрон свободен для новой привязки.",
            reply_markup=kb.team_card_kb(code, members=[], is_admin=False),
        )
        return
    await callback.message.edit_text(text, reply_markup=kb.team_card_kb(code, members=members, is_admin=True))


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


async def _drone_team_label(drone):
    if not drone or not drone["team_code"]:
        return ""
    name = await db.get_team_name(drone["team_code"])
    return f" · команда {name or drone['team_code']}"


async def _send_chunked(message, lines, chunk_chars=3500):
    """Sends `lines` as one or more messages, never splitting a single
    line's own '• ...' / indented continuation apart."""
    buf = []
    length = 0
    for line in lines:
        add = len(line) + 1
        if length + add > chunk_chars and buf:
            await message.answer("\n".join(buf))
            buf = []
            length = 0
        buf.append(line)
        length += add
    if buf:
        await message.answer("\n".join(buf))


FIELD_ROLES = ("leader", "pilot")


async def _own_team_or_none(message, user):
    """For a leader/pilot: their team_code, after checking they're attached
    and telling them if not. Returns None if the caller should stop (either
    not attached, or not a valid role at all — handled by the caller)."""
    if not user["team_code"]:
        await message.answer("Сначала привяжитесь к дрону — нажмите /start.")
        return None
    return user["team_code"]


@router.message(F.text == "⚡ Генераторы")
async def list_generators(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user or user["role"] not in ("admin", "manager") + FIELD_ROLES:
        await message.answer("Нажмите /start")
        return

    own_only = user["role"] in FIELD_ROLES
    team_code = None
    if own_only:
        team_code = await _own_team_or_none(message, user)
        if team_code is None:
            return

    generators = await db.list_generators(team_code=team_code)
    if not generators:
        msg = "Данные генератора ещё не внесены." if own_only else "Пока ни один генератор не внесён."
        await message.answer(msg)
        return

    title = "⚡ <b>Ваш генератор</b>" if own_only else f"⚡ <b>Генераторы парка ({len(generators)})</b>"
    lines = [title, ""]
    for g in generators:
        team_label = ""
        if not own_only:
            drone = await db.get_drone(g["drone_serial"])
            team_label = await _drone_team_label(drone)
        status, remaining = utils.generator_oil_status(
            g["work_hours"], g["oil_change_interval_hours"], g["last_oil_change_hours"]
        )
        rem_txt = f", осталось {utils.fmt_num(remaining, ' ч')}" if remaining is not None else ""
        lines.append(f"• S/N <code>{g['serial']}</code> — дрон {g['drone_serial']}{team_label}")
        lines.append(f"  Моточасы: {utils.fmt_num(g['work_hours'], ' ч')} · {status}{rem_txt}")
    await _send_chunked(message, lines)


@router.message(F.text == "🔋 Батареи")
async def list_batteries(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user or user["role"] not in ("admin", "manager") + FIELD_ROLES:
        await message.answer("Нажмите /start")
        return

    own_only = user["role"] in FIELD_ROLES
    team_code = None
    if own_only:
        team_code = await _own_team_or_none(message, user)
        if team_code is None:
            return

    batteries = await db.list_batteries(team_code=team_code)
    if not batteries:
        msg = "Данные батарей ещё не внесены." if own_only else "Пока ни одна батарея не внесена."
        await message.answer(msg)
        return

    title = f"🔋 <b>Ваши батареи ({len(batteries)})</b>" if own_only else f"🔋 <b>Батареи парка ({len(batteries)})</b>"
    lines = [title, ""]
    for b in batteries:
        team_label = ""
        if not own_only:
            drone = await db.get_drone(b["drone_serial"])
            team_label = await _drone_team_label(drone)
        status, remaining = utils.battery_status(b["cycles"], b["resource_cycles"])
        rem_txt = f", осталось {remaining} циклов" if remaining is not None else ""
        lines.append(f"• S/N <code>{b['serial']}</code> (слот {b['slot']}) — дрон {b['drone_serial']}{team_label}")
        lines.append(f"  Циклы: {utils.fmt_num(b['cycles'])}{rem_txt} — {status}")
    await _send_chunked(message, lines)


@router.message(F.text == "🚗 Автомобили")
async def list_vehicles(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user or user["role"] not in ("admin", "manager") + FIELD_ROLES:
        await message.answer("Нажмите /start")
        return

    own_only = user["role"] in FIELD_ROLES
    team_code = None
    if own_only:
        team_code = await _own_team_or_none(message, user)
        if team_code is None:
            return

    vehicles = await db.list_vehicles(team_code=team_code)
    if not vehicles:
        msg = "Данные автомобиля ещё не внесены." if own_only else "Пока ни один автомобиль не внесён."
        await message.answer(msg)
        return

    title = "🚗 <b>Ваш автомобиль</b>" if own_only else f"🚗 <b>Автомобили парка ({len(vehicles)})</b>"
    lines = [title, ""]
    for v in vehicles:
        team_label = ""
        if not own_only:
            drone = await db.get_drone(v["drone_serial"])
            team_label = await _drone_team_label(drone)
        status, remaining = utils.vehicle_oil_status(
            v["mileage_km"], v["oil_change_interval_km"], v["last_oil_change_km"]
        )
        rem_txt = f", осталось {utils.fmt_num(remaining, ' км')}" if remaining is not None else ""
        lines.append(
            f"• {v['manufacturer']} — гос.номер <code>{v['plate_number']}</code> — "
            f"дрон {v['drone_serial']}{team_label}"
        )
        lines.append(f"  Пробег: {utils.fmt_num(v['mileage_km'], ' км')}{rem_txt} — {status}")
    await _send_chunked(message, lines)


@router.message(F.text == "📊 Свод")
async def fleet_summary(message: Message):
    user = await db.get_user(message.from_user.id)
    if not _require_view(user):
        await message.answer("Этот раздел доступен администратору и менеджерам.")
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


def _member_label(member):
    if not member:
        return "не назначен"
    label = member["full_name"] or str(member["telegram_id"])
    if member["username"]:
        label += f" (@{member['username']})"
    return label


async def _format_team_equipment_block(code):
    """Full per-team equipment breakdown for '📊 Свод по командам':
    roster, drone, batteries (with status), generator and vehicle (with
    computed remaining-until-threshold phrasing)."""
    name = await db.get_team_name(code)
    header = f"Команда {name}" if name else f"Команда {code}"

    members = await db.list_team_members(code)
    leader = next((m for m in members if m["role"] == "leader"), None)
    pilots = [m for m in members if m["role"] == "pilot"]

    lines = [header, f"Руководитель: {_member_label(leader)}"]
    if pilots:
        for p in pilots:
            lines.append(f"Пилот: {_member_label(p)}")
    else:
        lines.append("Пилот: не назначен")

    drone_serial = await db.get_team_drone_serial(code)
    drone = await db.get_drone(drone_serial) if drone_serial else None
    if drone:
        lines.append(f"Дрон: {drone['model']}")
        lines.append(f"Серийный номер: {drone['serial']}")
    else:
        lines.append("Дрон: не привязан")

    batteries = await db.get_batteries(drone_serial) if drone_serial else []
    if batteries:
        for b in batteries:
            lines.append(f"🔋 Батарейка {b['slot']}: {b['serial']}")
            lines.append(f"Количество циклов: {utils.fmt_num(b['cycles'])}")
            status, _ = utils.battery_status(b["cycles"], b["resource_cycles"])
            lines.append(utils.display_battery_status(status))
    else:
        lines.append("🔋 Батареи: данные ещё не внесены")

    generator = await db.get_generator(drone["generator_serial"]) if drone and drone["generator_serial"] else None
    lines.append("")
    if generator:
        gen_label = f"{generator['manufacturer']}" if generator["manufacturer"] else ""
        lines.append(f"⚡️ Генератор: {gen_label}".rstrip())
        lines.append(f"Серийный номер: {generator['serial']}")
        lines.append(f"Состояние: {utils.generator_status_text(generator)}")
    else:
        lines.append("⚡️ Генератор: данные ещё не внесены")

    vehicle = await db.get_vehicle(drone["vehicle_plate"]) if drone and drone["vehicle_plate"] else None
    lines.append("")
    if vehicle:
        lines.append(f"🚗 Автомобиль: {vehicle['plate_number']}")
        lines.append(utils.vehicle_status_text(vehicle))
    else:
        lines.append("🚗 Автомобиль: данные ещё не внесены")

    return "\n".join(lines)


@router.message(F.text == "📊 Свод по командам")
async def teams_equipment_summary(message: Message):
    user = await db.get_user(message.from_user.id)
    if not _require_view(user):
        await message.answer("Этот раздел доступен администратору и менеджерам.")
        return
    teams = await db.list_claimed_teams()
    if not teams:
        await message.answer("Пока ни одна команда не привязана к дрону.")
        return
    lines = ["📊 <b>Свод по командам</b>"]
    for code in teams:
        lines.append("")
        lines.append(await _format_team_equipment_block(code))
    await _send_chunked(message, lines)
