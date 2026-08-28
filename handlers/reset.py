"""Admin-only: /reset wipes all test data (registrations, team claims,
equipment entries, reports, wash videos) and restores the 17-drone fleet to
its original Excel-seeded values with nothing attached — for clearing out
data entered while testing, before the bot goes live for real."""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import db
from handlers.common import send_main_menu

router = Router()


def _confirm_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⚠️ Да, стереть всё", callback_data="reset:confirm"))
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="reset:cancel"))
    return builder.as_markup()


@router.message(Command("reset"))
async def reset_start(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user or user["role"] != "admin":
        return  # silently ignore for non-admins, same as /promote
    await message.answer(
        "⚠️ <b>Полный сброс данных</b>\n\n"
        "Будут безвозвратно удалены:\n"
        "  • все регистрации — руководители, пилоты, менеджеры, необработанные "
        "заявки (кроме вашей учётной записи);\n"
        "  • привязки дронов к командам;\n"
        "  • все внесённые генераторы, батареи, автомобили;\n"
        "  • все отчёты и видео промывки.\n\n"
        "Список из 17 дронов (серийные номера, модель, налёт) останется — он будет "
        "восстановлен к исходным значениям из вашей таблицы «Дрон свод.xlsx».\n\n"
        "Это действие нельзя отменить. Продолжить?",
        reply_markup=_confirm_kb(),
    )


@router.callback_query(F.data == "reset:cancel")
async def reset_cancel(callback: CallbackQuery):
    await callback.message.edit_text("Отменено, данные не тронуты.")
    await callback.answer()


@router.callback_query(F.data == "reset:confirm")
async def reset_confirm(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    if not user or user["role"] != "admin":
        await callback.answer("Только для администратора", show_alert=True)
        return

    await db.reset_test_data(keep_telegram_id=callback.from_user.id)

    await callback.message.edit_text(
        "✅ Готово. Все регистрации, команды, техника, отчёты и видео промывки удалены.\n"
        "Список из 17 дронов восстановлен к исходным данным из таблицы.\n\n"
        "Вы остались администратором. Теперь можно рассылать ссылку на бота "
        "руководителям, пилотам и менеджерам заново."
    )
    await callback.answer()

    fresh_user = await db.get_user(callback.from_user.id)
    await send_main_menu(callback.message, fresh_user)
