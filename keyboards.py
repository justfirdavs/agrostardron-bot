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
        [KeyboardButton(text="👤 Заявки на регистрацию")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def main_menu_manager() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="🚁 Дроны"), KeyboardButton(text="👥 Команды")],
        [KeyboardButton(text="📊 Свод"), KeyboardButton(text="📋 Отчёты")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def main_menu_field() -> ReplyKeyboardMarkup:
    """Leader/pilot menu — both can enter equipment data and submit reports."""
    kb = [
        [KeyboardButton(text="🚁 Мои дроны")],
        [KeyboardButton(text="📝 Отправить отчёт"), KeyboardButton(text="📋 Мои отчёты")],
        [KeyboardButton(text="⚙️ Данные дрона"), KeyboardButton(text="🚿 Промывка дрона")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def request_contact_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True
    )


def pending_list_kb(pending_users):
    builder = InlineKeyboardBuilder()
    for u in pending_users:
        label = u["full_name"] or str(u["telegram_id"])
        builder.row(InlineKeyboardButton(text=label, callback_data=f"reg:open:{u['telegram_id']}"))
    return builder.as_markup()


def role_assign_kb(telegram_id):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="👑 Руководитель", callback_data=f"reg:role:{telegram_id}:leader"))
    builder.row(InlineKeyboardButton(text="🧑‍✈️ Пилот", callback_data=f"reg:role:{telegram_id}:pilot"))
    builder.row(InlineKeyboardButton(text="🗂 Менеджер", callback_data=f"reg:role:{telegram_id}:manager"))
    builder.row(InlineKeyboardButton(text="❌ Отклонить заявку", callback_data=f"reg:reject:{telegram_id}"))
    return builder.as_markup()


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


def drone_card_kb(serial, is_admin=False, can_manage_equipment=False, has_team=False):
    builder = InlineKeyboardBuilder()
    if can_manage_equipment:
        builder.row(
            InlineKeyboardButton(text="🔧 Обновить показания", callback_data=f"upd:menu:{serial}")
        )
        builder.row(
            InlineKeyboardButton(text="✏️ Внести/изменить данные", callback_data=f"equip:start:{serial}")
        )
    if is_admin and has_team:
        builder.row(
            InlineKeyboardButton(text="🔓 Открепить от экипажа", callback_data=f"assign:unset:{serial}")
        )
    builder.row(
        InlineKeyboardButton(text="📋 Отчёты по этому дрону", callback_data=f"reports:drone:{serial}:0")
    )
    builder.row(InlineKeyboardButton(text="⬅️ К списку дронов", callback_data="drones_page:0"))
    return builder.as_markup()


def teams_list_kb(teams):
    """teams: rows with 'code' and optional 'name' (db.list_claimed_teams_with_names)."""
    builder = InlineKeyboardBuilder()
    for t in teams:
        label = t["name"] or f"Команда {t['code']}"
        builder.row(InlineKeyboardButton(text=label, callback_data=f"team:{t['code']}"))
    return builder.as_markup()


def team_card_kb(code, members=None, is_admin=False):
    builder = InlineKeyboardBuilder()
    if is_admin:
        builder.row(
            InlineKeyboardButton(text="✏️ Переименовать команду", callback_data=f"team_rename:{code}")
        )
        for m in members or []:
            builder.row(
                InlineKeyboardButton(
                    text=f"❌ Удалить {m['full_name']}",
                    callback_data=f"team_kick:{m['telegram_id']}:{code}",
                )
            )
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
