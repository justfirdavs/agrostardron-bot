from aiogram.types import (
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

PAGE_SIZE = 8


def main_menu_admin() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="🚁 Дроны"), KeyboardButton(text="👥 Команды")],
        [KeyboardButton(text="📊 Свод"), KeyboardButton(text="📋 Отчёты")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def main_menu_team(is_leader=False) -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="🚁 Мои дроны")],
        [KeyboardButton(text="📝 Отправить отчёт"), KeyboardButton(text="📋 Мои отчёты")],
    ]
    if is_leader:
        kb.append([KeyboardButton(text="⚙️ Данные дрона")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def leader_choice_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Я руководитель команды", callback_data="role:leader"))
    builder.row(InlineKeyboardButton(text="Я пилот", callback_data="role:pilot"))
    return builder.as_markup()


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True
    )


def drones_list_kb(drones, page=0, prefix="drone"):
    builder = InlineKeyboardBuilder()
    start = page * PAGE_SIZE
    chunk = drones[start:start + PAGE_SIZE]
    for d in chunk:
        team = f" · Команда {d['team_code']}" if d["team_code"] else ""
        builder.row(
            InlineKeyboardButton(
                text=f"{d['model']} · {d['serial']}{team}",
                callback_data=f"{prefix}:{d['serial']}",
            )
        )
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"drones_page:{page-1}"))
    if start + PAGE_SIZE < len(drones):
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"drones_page:{page+1}"))
    if nav:
        builder.row(*nav)
    return builder.as_markup()


def drone_card_kb(serial, is_admin, is_leader=False):
    builder = InlineKeyboardBuilder()
    if is_admin:
        builder.row(
            InlineKeyboardButton(text="👥 Назначить команду", callback_data=f"assign:menu:{serial}")
        )
        builder.row(
            InlineKeyboardButton(text="🔧 Обновить показания", callback_data=f"upd:menu:{serial}")
        )
    if is_leader:
        builder.row(
            InlineKeyboardButton(text="✏️ Внести/изменить данные", callback_data=f"equip:start:{serial}")
        )
    builder.row(
        InlineKeyboardButton(text="📋 Отчёты по этому дрону", callback_data=f"reports:drone:{serial}:0")
    )
    builder.row(InlineKeyboardButton(text="⬅️ К списку дронов", callback_data="drones_page:0"))
    return builder.as_markup()


def assign_team_kb(serial, teams):
    builder = InlineKeyboardBuilder()
    for t in teams:
        builder.row(InlineKeyboardButton(text=f"Команда {t['code']}", callback_data=f"assign:set:{serial}:{t['code']}"))
    builder.row(InlineKeyboardButton(text="🚫 Снять команду", callback_data=f"assign:unset:{serial}"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"drone:{serial}"))
    return builder.as_markup()


def teams_list_kb(teams):
    builder = InlineKeyboardBuilder()
    for t in teams:
        builder.row(InlineKeyboardButton(text=f"Команда {t['code']}", callback_data=f"team:{t['code']}"))
    return builder.as_markup()


def team_card_kb(code):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ К командам", callback_data="teams:list"))
    return builder.as_markup()


def update_menu_kb(drone):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✈️ Налёт (часы)", callback_data=f"upd:flighthours:{drone['serial']}"))
    builder.row(InlineKeyboardButton(text="🔁 Кол-во полётов", callback_data=f"upd:flightcount:{drone['serial']}"))
    if drone["generator_serial"]:
        builder.row(InlineKeyboardButton(text="⚡ Моточасы генератора", callback_data=f"upd:genhours:{drone['generator_serial']}"))
        builder.row(InlineKeyboardButton(text="🛢 Замена масла генератора (сейчас)", callback_data=f"upd:genoil:{drone['generator_serial']}"))
    if drone["vehicle_plate"]:
        builder.row(InlineKeyboardButton(text="🚗 Пробег авто", callback_data=f"upd:vehkm:{drone['vehicle_plate']}"))
        builder.row(InlineKeyboardButton(text="🛢 Замена масла авто (сейчас)", callback_data=f"upd:vehoil:{drone['vehicle_plate']}"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад к дрону", callback_data=f"drone:{drone['serial']}"))
    return builder.as_markup()


def update_battery_menu_kb(drone_serial, batteries):
    builder = InlineKeyboardBuilder()
    for b in batteries:
        builder.row(
            InlineKeyboardButton(
                text=f"🔋 Батарея {b['slot']} ({b['serial']}) — циклы",
                callback_data=f"upd:batcycles:{b['id']}",
            )
        )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"upd:menu:{drone_serial}"))
    return builder.as_markup()


def work_type_kb():
    types = ["Опрыскивание", "Дефолиация", "Десикация", "Подкормка", "Обработка от вредителей", "Другое"]
    builder = InlineKeyboardBuilder()
    for t in types:
        builder.row(InlineKeyboardButton(text=t, callback_data=f"report:work:{t}"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="report:cancel"))
    return builder.as_markup()


def skip_note_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Пропустить", callback_data="report:skip_note"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="report:cancel"))
    return builder.as_markup()


def media_done_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Готово, сохранить отчёт", callback_data="report:media_done"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="report:cancel"))
    return builder.as_markup()


def report_drones_kb(drones):
    builder = InlineKeyboardBuilder()
    for d in drones:
        builder.row(InlineKeyboardButton(text=f"{d['model']} · {d['serial']}", callback_data=f"report:drone:{d['serial']}"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="report:cancel"))
    return builder.as_markup()


def reports_list_kb(reports, page, total, base_cb):
    builder = InlineKeyboardBuilder()
    for r in reports:
        date = r["created_at"][:10]
        builder.row(
            InlineKeyboardButton(
                text=f"№{r['id']} · {date} · {r['drone_serial']} · {r['work_type']}",
                callback_data=f"reports:open:{r['id']}:{page}",
            )
        )
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"{base_cb}:{page-1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"{base_cb}:{page+1}"))
    if nav:
        builder.row(*nav)
    return builder.as_markup()


def back_to_report_list_kb(base_cb, page):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ К списку отчётов", callback_data=f"{base_cb}:{page}"))
    return builder.as_markup()
