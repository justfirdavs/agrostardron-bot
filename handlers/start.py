from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

import config
import db
import keyboards as kb
from states import Registration, PromoteFlow
from handlers.common import send_main_menu
from handlers import equipment

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = await db.get_user(message.from_user.id)
    if user:
        await message.answer("С возвращением! 👋")
        await send_main_menu(message, user)
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
            f"Вам доступен весь парк дронов, команды и все отчёты.",
        )
        user = await db.get_user(message.from_user.id)
        await send_main_menu(message, user)
        return

    await message.answer(
        "Добро пожаловать в бот <b>АгроСтарДрон</b>! 🚁\n\n"
        "Чтобы получить доступ к своим дронам и отправлять отчёты, "
        "введите код своей команды (его даёт администратор), например: <code>A</code>",
    )
    await state.set_state(Registration.waiting_team_code)


@router.message(Registration.waiting_team_code)
async def process_team_code(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    team = await db.get_team(code)
    if not team:
        await message.answer(
            "Такой команды не найдено. Проверьте код у администратора и попробуйте ещё раз."
        )
        return

    await state.update_data(team_code=code)
    await state.set_state(Registration.waiting_leader_choice)
    await message.answer(
        f"Команда <b>{code}</b> найдена. Кто вы в этой команде?",
        reply_markup=kb.leader_choice_kb(),
    )


@router.callback_query(Registration.waiting_leader_choice, F.data.in_({"role:leader", "role:pilot"}))
async def process_leader_choice(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    code = data["team_code"]
    is_leader = callback.data == "role:leader"

    await db.create_user(
        telegram_id=callback.from_user.id,
        full_name=callback.from_user.full_name,
        username=callback.from_user.username,
        role="team",
        team_code=code,
        is_leader=is_leader,
    )
    await state.clear()

    role_txt = "руководитель команды" if is_leader else "пилот"
    await callback.message.edit_text(f"Готово! Вы прикреплены к команде <b>{code}</b> как {role_txt}.")
    await callback.answer()

    user = await db.get_user(callback.from_user.id)
    await send_main_menu(callback.message, user)

    if is_leader:
        await equipment.maybe_start_wizard(callback.message, state, code)


@router.message(Command("whoami"))
async def cmd_whoami(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("Вы ещё не зарегистрированы. Нажмите /start")
        return
    if user["role"] == "admin":
        role = "Администратор"
    else:
        role = f"Команда {user['team_code']}" + (" (руководитель)" if user["is_leader"] else "")
    await message.answer(f"ID: <code>{message.from_user.id}</code>\nРоль: {role}")


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
        await send_main_menu(message, user)
    else:
        await message.answer("Отменено. Нажмите /start, чтобы начать заново.")
