"""Background jobs, run alongside polling:
- hourly reminder (22:00, 23:00, 00:00, 01:00 local) — nudge team members
  who haven't yet sent today's work report and/or wash video;
- morning digest (10:00 local) — tell every manager/admin, per team, the
  previous day's best work result and drone-wash status in one message,
  with the wash video attached right after (Telegram can't embed video
  inside a text message).

Uses a fixed Asia/Tashkent UTC+5 offset (no DST) instead of system tzdata,
so it doesn't depend on a tzdata package being present on the host.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import db
import utils

logger = logging.getLogger(__name__)

TASHKENT_TZ = timezone(timedelta(hours=5))

REMINDER_HOURS = (22, 23, 0, 1)
MORNING_HOUR, MORNING_MINUTE = 10, 0


def _now_local():
    return datetime.now(TASHKENT_TZ)


async def _sleep_until(hour, minute):
    now = _now_local()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    await asyncio.sleep((target - now).total_seconds())


async def _sleep_until_next_hour_in(hours):
    """Sleeps until the local clock next hits one of `hours` (0-23), at
    minute 0 — used for the 22:00-01:00 reminder window, which wraps past
    midnight."""
    now = _now_local()
    candidates = []
    for h in hours:
        target = now.replace(hour=h, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        candidates.append(target)
    target = min(candidates)
    await asyncio.sleep((target - now).total_seconds())


async def hourly_reminder_loop(bot):
    """Every hour from 22:00 to 01:00 local time, remind any member of a
    claimed team who hasn't yet sent today's work report and/or wash video."""
    while True:
        await _sleep_until_next_hour_in(REMINDER_HOURS)
        try:
            await _run_hourly_reminder(bot)
        except Exception:
            logger.exception("hourly_reminder_loop failed")
        await asyncio.sleep(60)  # step past the target minute so we don't refire immediately


async def _run_hourly_reminder(bot):
    today = _now_local().strftime("%Y-%m-%d")
    for team_code in await db.list_claimed_teams():
        needs_work_report = not await db.has_work_report_today(team_code, today)
        needs_wash = not await db.has_washed_today(team_code, today)
        if not needs_work_report and not needs_wash:
            continue

        lines = ["⏰ Напоминание: сегодня ещё не отправлено:"]
        if needs_work_report:
            lines.append("  • 🌾 Отчёт о работе")
        if needs_wash:
            lines.append("  • 🚿 Видео промывки дрона")
        text = "\n".join(lines)

        for m in await db.list_team_members(team_code):
            try:
                await bot.send_message(m["telegram_id"], text)
            except Exception:
                continue


async def digest_loop(bot):
    """Every day at 10:00 local time, send managers/admin one combined
    per-team message: yesterday's best work report + wash status."""
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


async def _format_team_digest_block(team_code, date_label, report_date):
    team_name = await db.get_team_name(team_code)
    header = team_name or f"Команда {team_code}"
    drone_serial = await db.get_team_drone_serial(team_code) or team_code

    lines = [f"📋 <b>{header}</b> (дрон {drone_serial}) — {date_label}", ""]

    work_reports = await db.get_work_reports_for_team_date(team_code, report_date)
    if work_reports:
        best = work_reports[0]  # ORDER BY area_ha DESC -> best result first
        note = f" (лучший из {len(work_reports)})" if len(work_reports) > 1 else ""
        lines.append(f"🌾 Работа{note}:")
        lines.append(utils.format_work_report(best))
    else:
        lines.append("🌾 Работа: отчёт не отправлен")

    wash_reports = await db.get_wash_reports_for_team_date(team_code, report_date)
    lines.append("")
    lines.append("🚿 Промывка дрона: ✅ выполнена" if wash_reports else "🚿 Промывка дрона: ⚠️ не выполнена")

    if not work_reports or not wash_reports:
        members = await db.list_team_members(team_code)
        leader = next((m for m in members if m["role"] == "leader"), None)
        pilots = [m for m in members if m["role"] == "pilot"]
        lines.append("")
        lines.append(f"Руководитель: {_contact(leader)}")
        if pilots:
            for i, p in enumerate(pilots, start=1):
                lines.append(f"Пилот {i}: {_contact(p)}")

    return "\n".join(lines), wash_reports


async def _run_digest(bot):
    yesterday = (_now_local() - timedelta(days=1)).strftime("%Y-%m-%d")
    date_label = datetime.strptime(yesterday, "%Y-%m-%d").strftime("%d.%m.%Y")

    teams = await db.list_claimed_teams()
    if not teams:
        return
    recipients = await db.list_managers_and_admins()
    if not recipients:
        return

    blocks = []
    wash_by_team = []
    for team_code in teams:
        block, wash_reports = await _format_team_digest_block(team_code, date_label, yesterday)
        blocks.append(block)
        if wash_reports:
            wash_by_team.append((team_code, wash_reports))

    header = f"📆 <b>Утренний свод за {date_label}</b>"
    for chunk in _chunk_entries(header, blocks):
        for r in recipients:
            try:
                await bot.send_message(r["telegram_id"], chunk)
            except Exception:
                continue

    # Telegram can't embed video inside a text message, so wash videos
    # follow right after the combined digest message(s) above.
    for team_code, wash_reports in wash_by_team:
        for r in recipients:
            try:
                for rep in wash_reports:
                    await bot.send_video(r["telegram_id"], rep["video_file_id"])
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
