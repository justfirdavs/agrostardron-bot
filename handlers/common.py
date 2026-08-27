import keyboards as kb
from config import COMPANY_NAME


async def send_main_menu(message, user):
    if user["role"] == "admin":
        await message.answer(
            f"Главное меню — {COMPANY_NAME} (админ)",
            reply_markup=kb.main_menu_admin(),
        )
    else:
        team_label = f" (команда {user['team_code']})" if user["team_code"] else ""
        role_label = " · руководитель" if user["is_leader"] else ""
        await message.answer(
            f"Главное меню{team_label}{role_label}",
            reply_markup=kb.main_menu_team(is_leader=bool(user["is_leader"])),
        )


def format_drone_card(drone, team_members, batteries, generator, vehicle, repair_stats, gen_repair_stats, recent_repairs):
    import utils

    lines = []
    lines.append(f"🚁 <b>{drone['manufacturer']} {drone['model']}</b>")
    lines.append(f"S/N: <code>{drone['serial']}</code>")
    lines.append(f"Налёт: {utils.fmt_num(drone['flight_hours'], ' ч')} · Полётов: {utils.fmt_num(drone['flight_count'])}")
    lines.append("")

    lines.append("<b>Команда</b>")
    if drone["team_code"]:
        lines.append(f"Команда {drone['team_code']}")
        if team_members:
            for m in team_members:
                tag = "👑 руководитель" if m["is_leader"] else "пилот"
                lines.append(f"  • {m['full_name']} ({tag})")
        else:
            lines.append("  Пока никто из команды не зарегистрирован в боте")
    else:
        lines.append("Команда не назначена")
    lines.append("")

    lines.append(f"<b>Батареи ({len(batteries)} шт. из 3)</b>")
    if batteries:
        for b in batteries:
            status, remaining = utils.battery_status(b["cycles"], b["resource_cycles"])
            rem_txt = f", осталось {remaining} циклов" if remaining is not None else ""
            lines.append(
                f"  {b['slot']}. S/N {b['serial']} — {utils.fmt_num(b['cycles'])} циклов{rem_txt} — {status}"
            )
    else:
        lines.append("  Данные ещё не внесены руководителем команды")
    lines.append("")

    lines.append("<b>Генератор</b>")
    if generator:
        oil_status, oil_left = utils.generator_oil_status(
            generator["work_hours"], generator["oil_change_interval_hours"], generator["last_oil_change_hours"]
        )
        lines.append(f"S/N {generator['serial']}")
        lines.append(f"Моточасы: {utils.fmt_num(generator['work_hours'], ' ч')}")
        lines.append(f"Масло: {oil_status}" + (f" (осталось {utils.fmt_num(oil_left, ' ч')})" if oil_left is not None else ""))
        if gen_repair_stats and gen_repair_stats["c"]:
            lines.append(f"Ремонтов: {gen_repair_stats['c']} (последний: {gen_repair_stats['last_date'] or '—'})")
    else:
        lines.append("Данные ещё не внесены руководителем команды")
    lines.append("")

    lines.append("<b>Автомобиль</b>")
    if vehicle:
        veh_status, veh_left = utils.vehicle_oil_status(
            vehicle["mileage_km"], vehicle["oil_change_interval_km"], vehicle["last_oil_change_km"]
        )
        lines.append(f"{vehicle['manufacturer']} — гос.номер {vehicle['plate_number']}")
        lines.append(f"Пробег: {utils.fmt_num(vehicle['mileage_km'], ' км')}")
        lines.append(f"Масло: {veh_status}" + (f" (осталось {utils.fmt_num(veh_left, ' км')})" if veh_left is not None else ""))
    else:
        lines.append("Данные ещё не внесены руководителем команды")
    lines.append("")

    lines.append("<b>История ремонтов дрона</b>")
    if repair_stats and repair_stats["c"]:
        lines.append(f"Всего ремонтов: {repair_stats['c']} (последний: {repair_stats['last_date'] or '—'})")
        for r in recent_repairs[:3]:
            svc = utils.truncate(r["services"], 140)
            lines.append(f"  • №{r['act_number']} от {r['date']}: {svc}")
    else:
        lines.append("Ремонтов не было")

    return "\n".join(lines)
