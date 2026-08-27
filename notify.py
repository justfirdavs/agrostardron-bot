"""Automatic notifications when a battery/generator/vehicle status gets
worse (e.g. crosses into "Скоро замена" or "Заменить"). Called right after
any reading is entered/updated — there is nothing to poll in the background
since these values only change when a person types a new one in."""
from aiogram import Bot

import db
import utils


async def _notify_recipients(bot: Bot, drone_serial, text):
    ids = await db.get_notification_recipients(drone_serial)
    for tid in ids:
        try:
            await bot.send_message(tid, text)
        except Exception:
            continue


async def check_battery(bot: Bot, battery_id):
    battery = await db.get_battery(battery_id)
    if not battery or not battery["drone_serial"]:
        return
    status, remaining = utils.battery_status(battery["cycles"], battery["resource_cycles"])
    tier = utils.status_tier(status)
    old_tier = await db.get_battery_notified_tier(battery_id)
    if tier == old_tier:
        return
    await db.set_battery_notified_tier(battery_id, tier)
    if tier > old_tier:
        rem_txt = f" (осталось {remaining} циклов)" if remaining is not None else ""
        text = (
            f"⚠️ <b>Батарея требует внимания</b>\n"
            f"Дрон: {battery['drone_serial']}\n"
            f"Батарея S/N {battery['serial']}: {status}{rem_txt}"
        )
        await _notify_recipients(bot, battery["drone_serial"], text)


async def check_generator(bot: Bot, generator_serial):
    gen = await db.get_generator(generator_serial)
    if not gen or not gen["drone_serial"]:
        return
    status, remaining = utils.generator_oil_status(
        gen["work_hours"], gen["oil_change_interval_hours"], gen["last_oil_change_hours"]
    )
    tier = utils.status_tier(status)
    old_tier = await db.get_generator_notified_tier(generator_serial)
    if tier == old_tier:
        return
    await db.set_generator_notified_tier(generator_serial, tier)
    if tier > old_tier:
        rem_txt = f" (осталось {remaining} ч)" if remaining is not None else ""
        text = (
            f"⚠️ <b>Генератор требует внимания</b>\n"
            f"Дрон: {gen['drone_serial']}\n"
            f"Генератор S/N {gen['serial']}: {status}{rem_txt}"
        )
        await _notify_recipients(bot, gen["drone_serial"], text)


async def check_vehicle(bot: Bot, plate_number):
    veh = await db.get_vehicle(plate_number)
    if not veh or not veh["drone_serial"]:
        return
    status, remaining = utils.vehicle_oil_status(
        veh["mileage_km"], veh["oil_change_interval_km"], veh["last_oil_change_km"]
    )
    tier = utils.status_tier(status)
    old_tier = await db.get_vehicle_notified_tier(plate_number)
    if tier == old_tier:
        return
    await db.set_vehicle_notified_tier(plate_number, tier)
    if tier > old_tier:
        rem_txt = f" (осталось {remaining} км)" if remaining is not None else ""
        text = (
            f"⚠️ <b>Автомобиль требует внимания</b>\n"
            f"Дрон: {veh['drone_serial']}\n"
            f"Авто {veh['plate_number']}: {status}{rem_txt}"
        )
        await _notify_recipients(bot, veh["drone_serial"], text)
