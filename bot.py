import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

import config
import db
import scheduler
from handlers import start, drones, teams, updates, reports, equipment, registration, claim, wash

logging.basicConfig(level=logging.INFO)


async def main():
    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set. Put it in a .env file or env var.")

    await db.init_db()

    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start.router)
    dp.include_router(registration.router)
    dp.include_router(claim.router)
    dp.include_router(equipment.router)
    dp.include_router(wash.router)
    dp.include_router(drones.router)
    dp.include_router(teams.router)
    dp.include_router(updates.router)
    dp.include_router(reports.router)

    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(scheduler.evening_reminder_loop(bot))
    asyncio.create_task(scheduler.digest_loop(bot))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
