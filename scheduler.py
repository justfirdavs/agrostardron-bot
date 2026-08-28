"""Background jobs, run alongside polling:
- evening reminder (20:00 local) — nudge team members who haven't sent
  today's drone-wash video yet;
- morning digest (10:00 local) — tell every manager/admin which teams
  washed their drone yesterday (with the video) and which didn't.

Uses a fixed Asia/Tashkent UTC+5 offset (no DST) instead of system tzdata,
so it doesn't depend on a tzdata package being present on the host.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import db

logger = logging.getLogger(__name__)

TASHKENT_TZ = timezone(timedelta(hours=5))

EVENING_HOUR, EVENING_MINUTE = 20, 0
MORNING_HOUR, MORNING_MINUTE = 10, 0


def _now_local():
    return datetime.now(TASHKENT_TZ)


async def _sleep_until(hour, minute):
    now = _now_local()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    await asyncio.sleep((target - now).total_seconds())


async def evening_reminder_loop(bot):
    """Every day at 20:00 local time, remind any member of a claimed team
    who hasn't yet sent today's wash video."""
    while True:
        await _sleep_until(EVENING_HOUR, EVENING_MINUTE)
        try:
            await _run_evening_reminder(bot)
        except Exception:
            logger.exception("evening_reminder_loop failed")
        await asyncio.sleep(60)  # step past the target minute so we don't refire immediately


async def _run_evening_reminder(bot):
    today = _now_local().strftime("%Y-%m-%d")
    for team_code in await db.list_claimed_teams():
        if await db.has_washed_today(team_code, today):
            continue
        for m in await db.list_team_members(team_code):
            try:
                await bot.send_message(
                    m["telegram_id"],
                    "🚿 Напоминание: не забудьте промыть дрон после сегодняшних работ и "
                    "скинуть видео промывки боту — кнопка «🚿 Промывка дрона».",
                )
            except Exception:
                continue


async def digest_loop(bot):
    """Every day at 10:00 local time, tell managers/admin who washed their
    drone yesterday (with the video) and who didn't."""
    while True:
        await _sleep_until(MORNING_HOUR, MORNING_MINUTE)
        try:
            await _run_digest(bot)
        except Exception:
            logger.exception("digest_loop failed")
        await asyncio.sleep(60)


def _contact(member):
    if not member:
        return "не назначен"
    if member["username"]:
        return f"@{member['username']}"
    if member["phone"]:
        return member["phone"]
    return member["full_name"] or "контакт не указан"


async def _format_missing_entry(team_code, drone_serial):
    """'Команда A\n(дрон XXXX)\nРуководитель: @user\nПилот 1: @user1\n...'"""
    team_name = await db.get_team_name(team_code)
    header = team_name or f"Команда {team_code}"
    members = await db.list_team_members(team_code)
    leader = next((m for m in members if m["role"] == "leader"), None)
    pilots = [m for m in members if m["role"] == "pilot"]

    lines = [header, f"(дрон {drone_serial})", f"Руководитель: {_contact(leader)}"]
    if pilots:
        for i, p in enumerate(pilots, start=1):
            lines.append(f"Пилот {i}: {_contact(p)}")
    else:
        lines.append("Пилоты: не назначены")
    return "\n".join(lines)


async def _run_digest(bot):
    yesterday = (_now_local() - timedelta(days=1)).strftime("%Y-%m-%d")
    date_label = datetime.strptime(yesterday, "%Y-%m-%d").strftime("%d.%m.%Y")

    teams = await db.list_claimed_teams()
    if not teams:
        return
    recipients = await db.list_managers_and_admins()
    if not recipients:
        return

    missing = []
    for team_code in teams:
        reports = await db.get_wash_reports_for_team_date(team_code, yesterday)
        drone_serial = await db.get_team_drone_serial(team_code) or team_code
        if reports:
            caption = f"✅ Команда {team_code} промыла дрон {drone_serial} {date_label}"
            for r in recipients:
                try:
                    await bot.send_message(r["telegram_id"], caption)
                    for rep in reports:
                        await bot.send_video(r["telegram_id"], rep["video_file_id"])
                except Exception:
                    continue
        else:
            missing.append(await _format_missing_entry(team_code, drone_serial))

    if missing:
        for chunk in _chunk_entries(f"⚠️ Не промыли дрон {date_label}:", missing):
            for r in recipients:
                try:
                    await bot.send_message(r["telegram_id"], chunk)
                except Exception:
                    continue


def _chunk_entries(header, entries, sep="\n\n", limit=3500):
    """Groups entries into messages under Telegram's length limit, each
    prefixed with the header so a split digest still reads standalone."""
    chunks = []
    current = header
    for entry in entries:
        candidate = f"{current}{sep}{entry}"
        if len(candidate) > limit and current != header:
            chunks.append(current)
            current = f"{header}{sep}{entry}"
        else:
            current = candidate
    chunks.append(current)
    return chunks
