from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InputMediaPhoto, InputMediaVideo

import db
import keyboards as kb
from states import ReportFlow

router = Router()

PAGE_SIZE = kb.PAGE_SIZE
VIEW_ALL_ROLES = ("admin", "manager")


# ---------------- starting a report ----------------

@router.message(F.text == "📝 Отправить отчёт")
async def start_report(message: Message, state: FSMContext):
    user = await db.get_user(message.from_user.id)
    if not user or user["role"] not in ("leader", "pilot"):
        await message.answer("Отправка отчётов доступна руководителю и пилотам команды.")
        return
    if not user["team_code"]:
        await message.answer("Сначала привяжитесь к дрону — нажмите /start.")
        return

    drones = await db.list_drones(team_code=user["team_code"])
    if not drones:
        await message.answer("За вашей командой не закреплено ни одного дрона.")
        return

    await state.clear()
    if len(drones) == 1:
        await state.update_data(drone_serial=drones[0]["serial"], team_code=user["team_code"])
        await state.set_state(ReportFlow.choosing_work_type)
        await message.answer(
            f"Дрон: {drones[0]['model']} · {drones[0]['serial']}\n\nВыберите вид работ:",
            reply_markup=kb.work_type_kb(),
        )
        return

    await state.update_data(team_code=user["team_code"])
    await state.set_state(ReportFlow.choosing_drone)
    await message.answer("Выберите дрон:", reply_markup=kb.report_drones_kb(drones))


@router.callback_query(ReportFlow.choosing_drone, F.data.startswith("report:drone:"))
async def choose_drone(callback: CallbackQuery, state: FSMContext):
    serial = callback.data.split(":", 2)[2]
    await state.update_data(drone_serial=serial)
    await state.set_state(ReportFlow.choosing_work_type)
    await callback.message.edit_text(f"Дрон: {serial}\n\nВыберите вид работ:", reply_markup=kb.work_type_kb())
    await callback.answer()


@router.callback_query(ReportFlow.choosing_work_type, F.data.startswith("report:work:"))
async def choose_work_type(callback: CallbackQuery, state: FSMContext):
    work_type = callback.data.split(":", 2)[2]
    if work_type == "Другое":
        await state.set_state(ReportFlow.entering_work_type_custom)
        await callback.message.edit_text("Введите вид работ текстом:")
        await callback.answer()
        return
    await state.update_data(work_type=work_type)
    await state.set_state(ReportFlow.entering_location)
    await callback.message.edit_text(f"Вид работ: {work_type}\n\nВведите поле/локацию обработки:")
    await callback.answer()


@router.message(ReportFlow.entering_work_type_custom)
async def custom_work_type(message: Message, state: FSMContext):
    await state.update_data(work_type=message.text.strip())
    await state.set_state(ReportFlow.entering_location)
    await message.answer("Введите поле/локацию обработки:")


@router.message(ReportFlow.entering_location)
async def enter_location(message: Message, state: FSMContext):
    await state.update_data(location=message.text.strip())
    await state.set_state(ReportFlow.entering_area)
    await message.answer("Введите обработанную площадь (например: 30 Га):")


@router.message(ReportFlow.entering_area)
async def enter_area(message: Message, state: FSMContext):
    await state.update_data(area=message.text.strip())
    await state.set_state(ReportFlow.entering_note)
    await message.answer(
        "Добавьте комментарий (необязательно) или нажмите «Пропустить»:",
        reply_markup=kb.skip_note_kb(),
    )


@router.message(ReportFlow.entering_note)
async def enter_note(message: Message, state: FSMContext):
    await state.update_data(note=message.text.strip())
    await _ask_for_media(message, state)


@router.callback_query(ReportFlow.entering_note, F.data == "report:skip_note")
async def skip_note(callback: CallbackQuery, state: FSMContext):
    await state.update_data(note=None)
    await callback.message.edit_text("Комментарий пропущен.")
    await _ask_for_media(callback.message, state)
    await callback.answer()


async def _ask_for_media(message: Message, state: FSMContext):
    await state.update_data(media=[])
    await state.set_state(ReportFlow.collecting_media)
    await message.answer(
        "Прикрепите фото и/или видео с поля (можно несколько). "
        "Когда закончите — нажмите «Готово».",
        reply_markup=kb.media_done_kb(),
    )


@router.message(ReportFlow.collecting_media, F.photo)
async def collect_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    media = data.get("media", [])
    media.append({"file_id": message.photo[-1].file_id, "type": "photo"})
    await state.update_data(media=media)
    await message.answer(f"Фото добавлено ({len(media)}). Ещё, или нажмите «Готово».")


@router.message(ReportFlow.collecting_media, F.video)
async def collect_video(message: Message, state: FSMContext):
    data = await state.get_data()
    media = data.get("media", [])
    media.append({"file_id": message.video.file_id, "type": "video"})
    await state.update_data(media=media)
    await message.answer(f"Видео добавлено ({len(media)}). Ещё, или нажмите «Готово».")


@router.callback_query(ReportFlow.collecting_media, F.data == "report:media_done")
async def finish_report(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    user = await db.get_user(callback.from_user.id)

    report_id = await db.create_report(
        telegram_id=callback.from_user.id,
        team_code=data.get("team_code"),
        drone_serial=data.get("drone_serial"),
        work_type=data.get("work_type"),
        location=data.get("location"),
        area=data.get("area"),
        note=data.get("note"),
    )
    for m in data.get("media", []):
        await db.add_report_media(report_id, m["file_id"], m["type"])

    await state.clear()
    await callback.message.edit_text(f"✅ Отчёт №{report_id} сохранён. Спасибо!")
    await callback.answer()

    await _notify_admins(bot, report_id, user, data)


async def _notify_admins(bot: Bot, report_id, user, data):
    admins = await db.list_all_admins()
    if not admins:
        return
    text = (
        f"📝 <b>Новый отчёт №{report_id}</b>\n"
        f"Команда: {data.get('team_code')} · от {user['full_name'] if user else ''}\n"
        f"Дрон: {data.get('drone_serial')}\n"
        f"Вид работ: {data.get('work_type')}\n"
        f"Локация: {data.get('location')}\n"
        f"Площадь: {data.get('area')}\n"
    )
    if data.get("note"):
        text += f"Комментарий: {data['note']}\n"

    media = data.get("media", [])
    for admin in admins:
        try:
            await bot.send_message(admin["telegram_id"], text)
            await _send_media_group(bot, admin["telegram_id"], media)
        except Exception:
            continue


async def _send_media_group(bot: Bot, chat_id, media):
    if not media:
        return
    group = []
    for m in media[:10]:
        if m["type"] == "photo":
            group.append(InputMediaPhoto(media=m["file_id"]))
        else:
            group.append(InputMediaVideo(media=m["file_id"]))
    if len(group) == 1:
        item = group[0]
        if isinstance(item, InputMediaPhoto):
            await bot.send_photo(chat_id, item.media)
        else:
            await bot.send_video(chat_id, item.media)
    elif group:
        await bot.send_media_group(chat_id, group)
    # Telegram allows max 10 items per media group; extras beyond 10 are skipped here.


@router.callback_query(F.data == "report:cancel")
async def cancel_report(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Отчёт отменён.")
    await callback.answer()


# ---------------- viewing reports ----------------

@router.message(F.text.in_({"📋 Отчёты", "📋 Мои отчёты"}))
async def list_reports(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user:
        return
    if user["role"] not in VIEW_ALL_ROLES and not user["team_code"]:
        await message.answer("Сначала привяжитесь к дрону — нажмите /start.")
        return
    team_code = None if user["role"] in VIEW_ALL_ROLES else user["team_code"]
    total = await db.count_reports(team_code=team_code)
    if total == 0:
        await message.answer("Отчётов пока нет.")
        return
    reports = await db.list_reports(team_code=team_code, limit=PAGE_SIZE, offset=0)
    await message.answer(
        f"Отчёты (всего {total}):",
        reply_markup=kb.reports_list_kb(reports, page=0, total=total, base_cb="reports:page"),
    )


@router.callback_query(F.data.startswith("reports:page:"))
async def paginate_reports(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    page = int(callback.data.split(":")[2])
    team_code = None if user["role"] in VIEW_ALL_ROLES else user["team_code"]
    total = await db.count_reports(team_code=team_code)
    reports = await db.list_reports(team_code=team_code, limit=PAGE_SIZE, offset=page * PAGE_SIZE)
    await callback.message.edit_text(
        f"Отчёты (всего {total}):",
        reply_markup=kb.reports_list_kb(reports, page=page, total=total, base_cb="reports:page"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("reports:drone:"))
async def reports_for_drone(callback: CallbackQuery):
    _, _, serial, page = callback.data.split(":")
    page = int(page)
    user = await db.get_user(callback.from_user.id)
    if user["role"] not in VIEW_ALL_ROLES:
        drone = await db.get_drone(serial)
        if not drone or drone["team_code"] != user["team_code"]:
            await callback.answer("Нет доступа", show_alert=True)
            return
    total = await db.count_reports(drone_serial=serial)
    if total == 0:
        await callback.answer("По этому дрону пока нет отчётов", show_alert=True)
        return
    reports = await db.list_reports(drone_serial=serial, limit=PAGE_SIZE, offset=page * PAGE_SIZE)
    base_cb = f"reports:drone:{serial}"
    await callback.message.answer(
        f"Отчёты по дрону {serial} (всего {total}):",
        reply_markup=kb.reports_list_kb(reports, page=page, total=total, base_cb=base_cb),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("reports:open:"))
async def open_report(callback: CallbackQuery, bot: Bot):
    _, _, report_id, page = callback.data.split(":")
    report, media = await db.get_report(int(report_id))
    if not report:
        await callback.answer("Отчёт не найден", show_alert=True)
        return

    user = await db.get_user(callback.from_user.id)
    if user["role"] not in VIEW_ALL_ROLES and report["team_code"] != user["team_code"]:
        await callback.answer("Нет доступа", show_alert=True)
        return

    lines = [
        f"📝 <b>Отчёт №{report['id']}</b>",
        f"Дата: {report['created_at'][:16].replace('T', ' ')}",
        f"Команда: {report['team_code']}",
        f"Дрон: {report['drone_serial']}",
        f"Вид работ: {report['work_type']}",
        f"Локация: {report['location']}",
        f"Площадь: {report['area']}",
    ]
    if report["note"]:
        lines.append(f"Комментарий: {report['note']}")

    await callback.message.answer(
        "\n".join(lines),
        reply_markup=kb.back_to_report_list_kb("reports:page", int(page)),
    )

    photos = [InputMediaPhoto(media=m["file_id"]) for m in media if m["file_type"] == "photo"]
    videos = [m for m in media if m["file_type"] == "video"]

    if len(photos) == 1 and not videos:
        await callback.message.answer_photo(photos[0].media)
    elif photos:
        await bot.send_media_group(callback.from_user.id, photos[:10])
    for v in videos[:10]:
        await callback.message.answer_video(v["file_id"])

    await callback.answer()
