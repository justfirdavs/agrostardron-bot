"""Status/health calculations shared by handlers."""
from datetime import datetime

from config import (
    BATTERY_WARNING_CYCLES_LEFT,
    GENERATOR_OIL_WARNING_HOURS_LEFT,
    VEHICLE_OIL_WARNING_KM_LEFT,
)


def battery_status(cycles, resource_cycles):
    """Returns (label, remaining_cycles)."""
    if cycles is None or resource_cycles is None:
        return "⚪ Нет данных", None
    remaining = resource_cycles - cycles
    if remaining <= 0:
        return "🔴 Заменить", remaining
    if remaining <= BATTERY_WARNING_CYCLES_LEFT:
        return "🟡 Скоро замена", remaining
    return "🟢 Норма", remaining


def generator_oil_status(work_hours, interval_hours, last_change_hours):
    """Returns (label, remaining_hours)."""
    if work_hours is None or interval_hours is None or last_change_hours is None:
        return "⚪ Нет данных", None
    remaining = interval_hours - (work_hours - last_change_hours)
    if remaining <= 0:
        return "🔴 Пора менять масло", remaining
    if remaining <= GENERATOR_OIL_WARNING_HOURS_LEFT:
        return "🟡 Скоро замена масла", remaining
    return "🟢 Норма", remaining


def vehicle_oil_status(mileage_km, interval_km, last_change_km):
    """Returns (label, remaining_km)."""
    if mileage_km is None or interval_km is None or last_change_km is None:
        return "⚪ Нет данных", None
    remaining = interval_km - (mileage_km - last_change_km)
    if remaining <= 0:
        return "🔴 Пора менять масло", remaining
    if remaining <= VEHICLE_OIL_WARNING_KM_LEFT:
        return "🟡 Скоро замена масла", remaining
    return "🟢 Норма", remaining


def status_tier(label):
    """Maps a status label to a severity tier: 0 normal, 1 warning, 2 critical."""
    if "Заменить" in label or "Пора" in label:
        return 2
    if "Скоро" in label:
        return 1
    return 0


def fmt_num(v, suffix=""):
    if v is None:
        return "—"
    if isinstance(v, float):
        if v == int(v):
            v = int(v)
        else:
            v = round(v, 1)
    return f"{v}{suffix}"


def truncate(text, limit=220):
    if not text:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def format_work_report(report):
    """Renders a work_reports row the way team members type it themselves:

    📆09.09.2026
    📍Ферганская область, Учкуприкский район
    ⏳10:00-19:30
    (25л/га)
    49,8Га✅(комментарий, если есть)
    """
    try:
        date_txt = datetime.strptime(report["report_date"], "%Y-%m-%d").strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        date_txt = report["report_date"]

    lines = [
        f"📆{date_txt}",
        f"📍{report['location']}",
        f"⏳{report['time_range']}",
        f"({fmt_num(report['rate_l_ha'])}л/га)",
    ]
    area_line = f"{fmt_num(report['area_ha'])} Га✅"
    if report["comment"]:
        area_line += f" ({report['comment']})"
    lines.append(area_line)
    return "\n".join(lines)


def display_battery_status(label):
    """Same battery_status() label, reworded only for display in the
    'Свод по командам' report ('Заменить' -> 'Требуется замена') without
    touching the shared label text that status_tier() matches on."""
    return label.replace("Заменить", "Требуется замена")


def generator_status_text(generator):
    """'Состояние: приближается к порогу X ч (текущие: Y)' / 'Достиг порога
    X ч (текущие: Y). Требуется замена масла.' — the remaining-until-threshold
    phrasing for the per-team equipment summary. Doesn't touch
    generator_oil_status()/status_tier(), which stay untouched elsewhere."""
    if not generator:
        return "не назначен"
    work_hours = generator["work_hours"]
    interval = generator["oil_change_interval_hours"]
    last_change = generator["last_oil_change_hours"]
    if work_hours is None or interval is None or last_change is None:
        return "⚪ Нет данных"
    hours_since = work_hours - last_change
    threshold_txt = fmt_num(interval, " ч")
    current_txt = fmt_num(hours_since)
    if hours_since >= interval:
        return f"🔴 Достиг порога {threshold_txt} (текущие: {current_txt}). Требуется замена масла."
    remaining = interval - hours_since
    if remaining <= GENERATOR_OIL_WARNING_HOURS_LEFT:
        return f"🟡 Приближается к порогу {threshold_txt} (текущие: {current_txt})"
    return f"🟢 Норма (текущие: {current_txt} из {threshold_txt})"


def vehicle_status_text(vehicle):
    """Same idea as generator_status_text(), for vehicle mileage/oil."""
    if not vehicle:
        return "не назначен"
    mileage = vehicle["mileage_km"]
    interval = vehicle["oil_change_interval_km"]
    last_change = vehicle["last_oil_change_km"]
    if mileage is None or interval is None or last_change is None:
        return "⚪ Нет данных"
    km_since = mileage - last_change
    threshold_txt = fmt_num(interval, " км")
    current_txt = fmt_num(km_since, " км")
    if km_since >= interval:
        return f"🔴 Достиг порога {threshold_txt} (текущие: {current_txt}). Требуется замена масла."
    remaining = interval - km_since
    if remaining <= VEHICLE_OIL_WARNING_KM_LEFT:
        return f"🟡 Приближается к порогу {threshold_txt} (текущие: {current_txt})"
    return f"🟢 Норма (текущие: {current_txt} из {threshold_txt})"
