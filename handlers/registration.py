"""Admin-side: review registration requests and assign a role
(leader / pilot / manager) to whoever shared their phone number."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

import db
import keyboards as kb
from handlers.common import ROLE_LABELS

router = Router()


async def _require_admin(telegram_id):
    user = await db.get_user(telegram_id)
    return user and user["role"] == "admin"


@router.message(F.text == "👤 Заявки на регистрацию")
async def list_pending(message: Message):
    if not await _require_admin(message.from_user.id):
        await message.answer("Этот раздел доступен только администратору.")
        return
    pending = await db.list_pending_users()
    if not pending:
        await message.answer("Новых заявок нет.")
        return
    await message.answer(
        f"Заявок на рассмотрении: {len(pending)}. Выберите, кому назначить роль:",
        reply_markup=kb.pending_list_kb(pending),
    )


@router.callback_query(F.data.startswith("reg:open:"))
async def open_pending(callback: CallbackQuery):
    if not await _require_admin(callback.from_user.id):
        await callback.answer("Только для администратора", show_alert=True)
        return
    target_id = int(callback.data.split(":", 2)[2])
    target = await db.get_user(target_id)
    if not target:
        await callback.answer("Заявка не найдена (возможно, уже обработана)", show_alert=True)
        return
    text = (
        f"👤 <b>{target['full_name']}</b>\n"
        f"Username: @{target['username'] or '—'}\n"
        f"Телефон: {target['phone'] or '—'}\n\n"
        f"Назначьте роль:"
    )
    try:
        await callback.message.edit_text(text, reply_markup=kb.role_assign_kb(target_id))
    except Exception:
        await callback.message.answer(text, reply_markup=kb.role_assign_kb(target_id))
    await callback.answer()


@router.callback_query(F.data.startswith("reg:role:"))
async def pick_role(callback: CallbackQuery):
    if not await _require_admin(callback.from_user.id):
        await callback.answer("Только для администратора", show_alert=True)
        return
    _, _, target_id, role = callback.data.split(":")
    await _finalize(callback, int(target_id), role)


@router.callback_query(F.data.startswith("reg:reject:"))
async def reject(callback: CallbackQuery):
    if not await _require_admin(callback.from_user.id):
        await callback.answer("Только для администратора", show_alert=True)
        return
    target_id = int(callback.data.split(":", 2)[2])
    await db.delete_user(target_id)
    await callback.message.edit_text("Заявка отклонена.")
    await callback.answer()
    try:
        await callback.bot.send_message(
            target_id, "Ваша заявка на регистрацию отклонена. Если это ошибка — напишите администратору."
        )
    except Exception:
        pass


async def _finalize(callback: CallbackQuery, target_id: int, role: str):
    await db.approve_user(target_id, role, team_code=None)
    await callback.message.edit_text(f"✅ Роль назначена: {ROLE_LABELS[role]}")
    await callback.answer()

    if role == "leader":
        extra = (
            "\n\nНажмите /start и введите серийный номер дрона вашей команды — "
            "бот попросит внести данные генератора, батарей и автомобиля."
        )
    elif role == "pilot":
        extra = (
            "\n\nНажмите /start и введите серийный номер дрона вашей команды — "
            "система автоматически привяжет вас к ней."
        )
    else:
        extra = "\n\nНажмите /start, чтобы открыть меню."

    user_text = f"🎉 Ваша заявка одобрена!\nВаша роль: <b>{ROLE_LABELS[role]}</b>.{extra}"
    try:
        await callback.bot.send_message(target_id, user_text)
    except Exception:
        pass
