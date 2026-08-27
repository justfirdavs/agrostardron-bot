from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

import config
import db
import keyboards as kb
from states import PromoteFlow
from handlers.common import send_main_menu

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = await db.get_user(message.from_user.id)
    if user:
        await message.answer("С возвращением! 👋")
        await send_main_menu(message, user, state)
        return

    # No account yet. Decide role.
    is_forced_admin = message.from_user.id in config.ADMIN_IDS
    no_admin_yet = not await db.any_admin_exists()

    if is_forced_admin or no_admin_yet:
        await db.create_user(
            telegram_id=message.from_user.id,
            full_name=message.from_user.full_name,
            username=message.from_user.username,
            role="admin",
        )
        await message.answer(
            f"Добро пожаловать, {message.from_user.full_name}!\n\n"
            f"Вы зарегистрированы как <b>администратор</b> бота {config.COMPANY_NAME}.\n"
            f"Вам доступен весь парк дронов, команды, заявки и все отчёты.",
        )
        user = await db.get_user(message.from_user.id)
        await send_main_menu(message, user, state)
        return

    await message.answer(
        "Добро пожаловать в бот <b>АгроСтарДрон</b>! 🚁\n\n"
        "Для регистрации поделитесь своим номером телефона — нажмите кнопку "
        "ниже. Заявка уйдёт администратору, он назначит вам роль (руководитель, "
        "пилот или менеджер).",
        reply_markup=kb.request_contact_kb(),
    )


@router.message(F.contact)
async def receive_contact(message: Message, bot: Bot, state: FSMContext):
    if not message.contact or message.contact.user_id != message.from_user.id:
        await message.answer("Пожалуйста, поделитесь именно своим номером телефона.")
        return

    existing = await db.get_user(message.from_user.id)
    if existing:
        await message.answer("Вы уже зарегистрированы.", reply_markup=ReplyKeyboardRemove())
        await send_main_menu(message, existing, state)
        return

    await db.create_pending_user(
        telegram_id=message.from_user.id,
        full_name=message.from_user.full_name,
        username=message.from_user.username,
        phone=message.contact.phone_number,
    )
    await message.answer(
        "Спасибо! Заявка отправлена администратору. Как только он назначит "
        "вам роль, вы получите уведомление здесь.",
        reply_markup=ReplyKeyboardRemove(),
    )

    admins = await db.list_all_admins()
    text = (
        f"🆕 <b>Новая заявка на регистрацию</b>\n"
        f"Имя: {message.from_user.full_name}\n"
        f"Username: @{message.from_user.username or '—'}\n"
        f"Телефон: {message.contact.phone_number}\n\n"
        f"Назначьте роль:"
    )
    for admin in admins:
        try:
            await bot.send_message(
                admin["telegram_id"], text, reply_markup=kb.role_assign_kb(message.from_user.id)
            )
        except Exception:
            continue


@router.message(Command("whoami"))
async def cmd_whoami(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("Вы ещё не зарегистрированы. Нажмите /start")
        return
    from handlers.common import ROLE_LABELS

    role = ROLE_LABELS.get(user["role"], "заявка на рассмотрении")
    team = f" · команда {user['team_code']}" if user["team_code"] else ""
    await message.answer(f"ID: <code>{message.from_user.id}</code>\nРоль: {role}{team}")


@router.message(Command("promote"))
async def cmd_promote(message: Message, command: CommandObject, state: FSMContext):
    user = await db.get_user(message.from_user.id)
    if not user or user["role"] != "admin":
        return  # silently ignore for non-admins

    if command.args and command.args.strip().isdigit():
        target_id = int(command.args.strip())
        await _promote_id(message, target_id)
        return

    await message.answer(
        "Пришлите Telegram ID пользователя, которого нужно сделать администратором.\n"
        "Узнать свой ID человек может у бота @userinfobot."
    )
    await state.set_state(PromoteFlow.waiting_id)


@router.message(PromoteFlow.waiting_id)
async def promote_receive_id(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("Это не похоже на числовой ID. Пришлите число или /cancel")
        return
    await _promote_id(message, int(text))
    await state.clear()


async def _promote_id(message: Message, target_id: int):
    target = await db.get_user(target_id)
    if not target:
        await message.answer(
            "Такой пользователь ещё не запускал бота. Попросите его сначала нажать /start."
        )
        return
    await db.set_user_role(target_id, "admin")
    await message.answer(f"Пользователь {target_id} назначен администратором ✅")


@router.message(Command("cancel"))
@router.message(F.text == "❌ Отмена")
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    user = await db.get_user(message.from_user.id)
    if user:
        await message.answer("Отменено.")
        await send_main_menu(message, user, state)
    else:
        await message.answer("Отменено. Нажмите /start, чтобы начать заново.")
