"""Status/health calculations shared by handlers."""
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
