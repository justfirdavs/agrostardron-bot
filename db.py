"""All database access lives here: schema, seeding from the Excel-derived
JSON fixture, and query helpers used by the handlers."""
import json
import os
from datetime import datetime

import aiosqlite

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    code TEXT PRIMARY KEY,
    name TEXT
);

CREATE TABLE IF NOT EXISTS drones (
    serial TEXT PRIMARY KEY,
    manufacturer TEXT,
    model TEXT,
    flight_hours REAL,
    flight_count INTEGER,
    team_code TEXT,
    vehicle_plate TEXT,
    generator_serial TEXT
);

CREATE TABLE IF NOT EXISTS batteries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    serial TEXT,
    manufacturer TEXT,
    model TEXT,
    cycles INTEGER,
    resource_cycles INTEGER DEFAULT 800,
    drone_serial TEXT,
    slot INTEGER,
    last_notified_tier INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS generators (
    serial TEXT PRIMARY KEY,
    manufacturer TEXT,
    model TEXT,
    work_hours REAL,
    oil_change_interval_hours REAL DEFAULT 50,
    last_oil_change_hours REAL,
    repairs_count INTEGER DEFAULT 0,
    drone_serial TEXT,
    last_notified_tier INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS vehicles (
    plate_number TEXT PRIMARY KEY,
    manufacturer TEXT,
    tech_passport TEXT,
    vin TEXT,
    mileage_km REAL,
    oil_change_interval_km REAL DEFAULT 10000,
    last_oil_change_km REAL,
    drone_serial TEXT,
    last_notified_tier INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS drone_repairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    act_number INTEGER,
    date TEXT,
    drone_serial TEXT,
    services TEXT
);

CREATE TABLE IF NOT EXISTS generator_repairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    act_number INTEGER,
    date TEXT,
    generator_serial TEXT,
    services TEXT
);

CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    full_name TEXT,
    username TEXT,
    phone TEXT,
    role TEXT,
    team_code TEXT,
    is_leader INTEGER DEFAULT 0,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER,
    team_code TEXT,
    drone_serial TEXT,
    work_type TEXT,
    location TEXT,
    area TEXT,
    note TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS report_media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER,
    file_id TEXT,
    file_type TEXT
);

CREATE TABLE IF NOT EXISTS wash_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_code TEXT,
    drone_serial TEXT,
    telegram_id INTEGER,
    video_file_id TEXT,
    wash_date TEXT,
    created_at TEXT
);
"""

_db: aiosqlite.Connection | None = None


async def get_conn() -> aiosqlite.Connection:
    global _db
    if _db is None:
        os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
        _db = await aiosqlite.connect(config.DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA foreign_keys = ON;")
    return _db


async def init_db():
    conn = await get_conn()
    await conn.executescript(SCHEMA)
    await conn.commit()
    await _migrate(conn)
    await seed_if_empty()


async def _add_column_if_missing(conn, table, column, coldef):
    cur = await conn.execute(f"PRAGMA table_info({table})")
    cols = {row["name"] for row in await cur.fetchall()}
    if column not in cols:
        await conn.execute(f"ALTER TABLE {table} ADD COLUMN {coldef}")


async def _migrate(conn):
    """Idempotent, additive migration so an already-running deployment
    picks up new columns/roles without losing existing data."""
    await _add_column_if_missing(conn, "users", "phone", "phone TEXT")
    await _add_column_if_missing(conn, "batteries", "last_notified_tier", "last_notified_tier INTEGER DEFAULT 0")
    await _add_column_if_missing(conn, "generators", "last_notified_tier", "last_notified_tier INTEGER DEFAULT 0")
    await _add_column_if_missing(conn, "vehicles", "last_notified_tier", "last_notified_tier INTEGER DEFAULT 0")
    await _add_column_if_missing(conn, "teams", "name", "name TEXT")

    # Old model: role in ('admin', 'team') + is_leader flag.
    # New model: role in ('admin', 'leader', 'pilot', 'manager', 'pending').
    await conn.execute("UPDATE users SET role = 'leader' WHERE role = 'team' AND is_leader = 1")
    await conn.execute("UPDATE users SET role = 'pilot' WHERE role = 'team' AND (is_leader = 0 OR is_leader IS NULL)")
    await conn.commit()

    await _uppercase_serials(conn)


async def _uppercase_serials(conn):
    """One-time normalization: serial numbers are always stored uppercase
    (543f62d -> 543F62D), so a self-claim by serial always matches the
    seeded drone list regardless of how someone typed it, and cascades the
    change to every place that references a drone/generator serial."""
    cur = await conn.execute("SELECT serial FROM drones")
    for row in await cur.fetchall():
        old = row["serial"]
        new = old.upper()
        if new == old:
            continue
        await conn.execute("UPDATE drones SET serial = ? WHERE serial = ?", (new, old))
        await conn.execute("UPDATE drones SET team_code = ? WHERE team_code = ?", (new, old))
        await conn.execute("UPDATE users SET team_code = ? WHERE team_code = ?", (new, old))
        await conn.execute("UPDATE teams SET code = ? WHERE code = ?", (new, old))
        await conn.execute("UPDATE batteries SET drone_serial = ? WHERE drone_serial = ?", (new, old))
        await conn.execute("UPDATE generators SET drone_serial = ? WHERE drone_serial = ?", (new, old))
        await conn.execute("UPDATE vehicles SET drone_serial = ? WHERE drone_serial = ?", (new, old))
        await conn.execute("UPDATE drone_repairs SET drone_serial = ? WHERE drone_serial = ?", (new, old))
        await conn.execute("UPDATE reports SET drone_serial = ? WHERE drone_serial = ?", (new, old))
        await conn.execute("UPDATE reports SET team_code = ? WHERE team_code = ?", (new, old))
        await conn.execute("UPDATE wash_reports SET drone_serial = ? WHERE drone_serial = ?", (new, old))
        await conn.execute("UPDATE wash_reports SET team_code = ? WHERE team_code = ?", (new, old))

    cur = await conn.execute("SELECT serial FROM generators")
    for row in await cur.fetchall():
        old = row["serial"]
        new = old.upper()
        if new == old:
            continue
        await conn.execute("UPDATE generators SET serial = ? WHERE serial = ?", (new, old))
        await conn.execute("UPDATE drones SET generator_serial = ? WHERE generator_serial = ?", (new, old))
        await conn.execute(
            "UPDATE generator_repairs SET generator_serial = ? WHERE generator_serial = ?", (new, old)
        )

    await conn.execute("UPDATE batteries SET serial = UPPER(serial) WHERE serial IS NOT NULL")
    await conn.execute("UPDATE vehicles SET vin = UPPER(vin) WHERE vin IS NOT NULL")
    await conn.commit()


async def seed_if_empty():
    """Seed only the data confirmed real: team codes, the drone fleet
    (serial/manufacturer/model/flight hours), and drone repair history.
    Batteries, generators, vehicles and team rosters are intentionally NOT
    seeded — that placeholder data gets replaced by real entries typed in
    by team leaders and the admin through the bot itself."""
    conn = await get_conn()
    cur = await conn.execute("SELECT COUNT(*) AS c FROM drones")
    row = await cur.fetchone()
    if row["c"] > 0:
        return  # already seeded

    if not os.path.exists(config.SEED_FILE):
        return

    with open(config.SEED_FILE, encoding="utf-8") as f:
        data = json.load(f)

    for t in data["teams"]:
        await conn.execute("INSERT OR IGNORE INTO teams (code) VALUES (?)", (t["code"],))

    for serial, d in data["drones"].items():
        await conn.execute(
            "INSERT OR IGNORE INTO drones "
            "(serial, manufacturer, model, flight_hours, flight_count, team_code, "
            "vehicle_plate, generator_serial) VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL)",
            (
                serial,
                d["manufacturer"],
                d["model"],
                d["flight_hours"],
                d["flight_count"],
            ),
        )

    for r in data["drone_repairs"]:
        await conn.execute(
            "INSERT INTO drone_repairs (act_number, date, drone_serial, services) "
            "VALUES (?, ?, ?, ?)",
            (r["act_number"], r["date"], r["serial"], r["services"]),
        )

    await conn.commit()


# ---------- users ----------

async def get_user(telegram_id: int):
    conn = await get_conn()
    cur = await conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    return await cur.fetchone()


async def any_admin_exists() -> bool:
    conn = await get_conn()
    cur = await conn.execute("SELECT COUNT(*) AS c FROM users WHERE role = 'admin'")
    row = await cur.fetchone()
    return row["c"] > 0


async def create_user(telegram_id, full_name, username, role, team_code=None, phone=None):
    conn = await get_conn()
    is_leader = 1 if role == "leader" else 0
    await conn.execute(
        "INSERT OR REPLACE INTO users (telegram_id, full_name, username, phone, role, "
        "team_code, is_leader, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (telegram_id, full_name, username, phone, role, team_code, is_leader, datetime.utcnow().isoformat()),
    )
    await conn.commit()


async def create_pending_user(telegram_id, full_name, username, phone):
    """A brand-new contact-share registration, awaiting the admin to assign a role."""
    await create_user(telegram_id, full_name, username, role="pending", team_code=None, phone=phone)


async def approve_user(telegram_id, role, team_code=None):
    conn = await get_conn()
    is_leader = 1 if role == "leader" else 0
    await conn.execute(
        "UPDATE users SET role = ?, team_code = ?, is_leader = ? WHERE telegram_id = ?",
        (role, team_code, is_leader, telegram_id),
    )
    await conn.commit()


async def set_user_role(telegram_id, role):
    conn = await get_conn()
    is_leader = 1 if role == "leader" else 0
    await conn.execute(
        "UPDATE users SET role = ?, is_leader = ? WHERE telegram_id = ?", (role, is_leader, telegram_id)
    )
    await conn.commit()


async def set_user_team_code(telegram_id, team_code):
    conn = await get_conn()
    await conn.execute(
        "UPDATE users SET team_code = ? WHERE telegram_id = ?", (team_code, telegram_id)
    )
    await conn.commit()


async def count_pilots_in_team(team_code):
    conn = await get_conn()
    cur = await conn.execute(
        "SELECT COUNT(*) AS c FROM users WHERE team_code = ? AND role = 'pilot'", (team_code,)
    )
    row = await cur.fetchone()
    return row["c"]


async def delete_user(telegram_id):
    conn = await get_conn()
    await conn.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
    await conn.commit()


async def list_pending_users():
    conn = await get_conn()
    cur = await conn.execute("SELECT * FROM users WHERE role = 'pending' ORDER BY created_at")
    return await cur.fetchall()


async def list_team_members(team_code):
    conn = await get_conn()
    cur = await conn.execute(
        "SELECT * FROM users WHERE team_code = ? AND role IN ('leader','pilot') "
        "ORDER BY is_leader DESC, full_name",
        (team_code,),
    )
    return await cur.fetchall()


async def get_team_leader(team_code):
    conn = await get_conn()
    cur = await conn.execute(
        "SELECT * FROM users WHERE team_code = ? AND role = 'leader' LIMIT 1", (team_code,)
    )
    return await cur.fetchone()


async def list_managers():
    conn = await get_conn()
    cur = await conn.execute("SELECT * FROM users WHERE role = 'manager' ORDER BY full_name")
    return await cur.fetchall()


async def can_edit_drone(telegram_id, drone_serial):
    """True if this user may enter/update equipment data and readings for this drone:
    the admin (any drone), or a leader/pilot attached to the drone's team."""
    user = await get_user(telegram_id)
    if not user:
        return False
    if user["role"] == "admin":
        return True
    if user["role"] not in ("leader", "pilot") or not user["team_code"]:
        return False
    drone = await get_drone(drone_serial)
    return bool(drone and drone["team_code"] and drone["team_code"] == user["team_code"])


async def get_notification_recipients(drone_serial):
    """Telegram IDs to notify about this drone's equipment status: its
    team's leader/pilots, plus every admin."""
    conn = await get_conn()
    drone = await get_drone(drone_serial)
    ids = set()
    if drone and drone["team_code"]:
        members = await list_team_members(drone["team_code"])
        ids.update(m["telegram_id"] for m in members)
    cur = await conn.execute("SELECT telegram_id FROM users WHERE role = 'admin'")
    ids.update(row["telegram_id"] for row in await cur.fetchall())
    return list(ids)


# ---------- teams ----------

async def get_team(code: str):
    conn = await get_conn()
    cur = await conn.execute("SELECT * FROM teams WHERE code = ?", (code,))
    return await cur.fetchone()


async def list_teams():
    conn = await get_conn()
    cur = await conn.execute("SELECT * FROM teams ORDER BY code")
    return await cur.fetchall()


async def list_claimed_teams():
    """Team codes that actually have a drone attached (a leader has claimed
    it), derived from the drones table rather than the now-vestigial
    pre-seeded `teams` table."""
    conn = await get_conn()
    cur = await conn.execute(
        "SELECT DISTINCT team_code FROM drones WHERE team_code IS NOT NULL ORDER BY team_code"
    )
    return [row["team_code"] for row in await cur.fetchall()]


async def get_team_drone_serial(team_code):
    """The serial of the (single) drone claimed by this team."""
    conn = await get_conn()
    cur = await conn.execute("SELECT serial FROM drones WHERE team_code = ? LIMIT 1", (team_code,))
    row = await cur.fetchone()
    return row["serial"] if row else None


async def list_claimed_teams_with_names():
    """Claimed team codes plus their optional admin-set display name, for
    admin/manager UI (list_claimed_teams stays name-free for internal
    scheduler/logic code that only needs the bare codes)."""
    conn = await get_conn()
    cur = await conn.execute(
        "SELECT d.team_code AS code, t.name AS name FROM "
        "(SELECT DISTINCT team_code FROM drones WHERE team_code IS NOT NULL) d "
        "LEFT JOIN teams t ON t.code = d.team_code ORDER BY d.team_code"
    )
    return await cur.fetchall()


async def get_team_name(team_code):
    conn = await get_conn()
    cur = await conn.execute("SELECT name FROM teams WHERE code = ?", (team_code,))
    row = await cur.fetchone()
    return row["name"] if row and row["name"] else None


async def set_team_name(team_code, name):
    conn = await get_conn()
    name = (name or "").strip() or None
    await conn.execute(
        "INSERT INTO teams (code, name) VALUES (?, ?) "
        "ON CONFLICT(code) DO UPDATE SET name = excluded.name",
        (team_code, name),
    )
    await conn.commit()


async def remove_team_member(telegram_id):
    """Detach a leader/pilot from their team (their approved role is kept,
    so they can self-claim again via /start). Removing the leader disbands
    the whole team: the drone is unclaimed and any pilots are detached too,
    so it can be claimed properly from scratch."""
    conn = await get_conn()
    user = await get_user(telegram_id)
    if not user or not user["team_code"]:
        return
    team_code = user["team_code"]
    was_leader = user["role"] == "leader"
    await conn.execute("UPDATE users SET team_code = NULL WHERE telegram_id = ?", (telegram_id,))
    await conn.commit()
    if was_leader:
        await conn.execute("UPDATE drones SET team_code = NULL WHERE team_code = ?", (team_code,))
        await conn.execute("UPDATE users SET team_code = NULL WHERE team_code = ?", (team_code,))
        await conn.commit()


async def list_managers_and_admins():
    conn = await get_conn()
    cur = await conn.execute("SELECT * FROM users WHERE role IN ('admin', 'manager')")
    return await cur.fetchall()


# ---------- drones ----------

async def list_drones(team_code=None):
    conn = await get_conn()
    if team_code:
        cur = await conn.execute(
            "SELECT * FROM drones WHERE team_code = ? ORDER BY serial", (team_code,)
        )
    else:
        cur = await conn.execute("SELECT * FROM drones ORDER BY serial")
    return await cur.fetchall()


async def get_drone(serial: str):
    conn = await get_conn()
    cur = await conn.execute("SELECT * FROM drones WHERE serial = ?", (serial,))
    return await cur.fetchone()


async def get_batteries(drone_serial: str):
    conn = await get_conn()
    cur = await conn.execute(
        "SELECT * FROM batteries WHERE drone_serial = ? ORDER BY slot", (drone_serial,)
    )
    return await cur.fetchall()


async def get_battery(battery_id: int):
    conn = await get_conn()
    cur = await conn.execute("SELECT * FROM batteries WHERE id = ?", (battery_id,))
    return await cur.fetchone()


async def get_generator(serial: str):
    conn = await get_conn()
    cur = await conn.execute("SELECT * FROM generators WHERE serial = ?", (serial,))
    return await cur.fetchone()


async def get_vehicle(plate: str):
    conn = await get_conn()
    cur = await conn.execute("SELECT * FROM vehicles WHERE plate_number = ?", (plate,))
    return await cur.fetchone()


async def get_drone_repairs(drone_serial: str, limit=5):
    conn = await get_conn()
    cur = await conn.execute(
        "SELECT * FROM drone_repairs WHERE drone_serial = ? ORDER BY date DESC, act_number DESC LIMIT ?",
        (drone_serial, limit),
    )
    return await cur.fetchall()


async def count_drone_repairs(drone_serial: str):
    conn = await get_conn()
    cur = await conn.execute(
        "SELECT COUNT(*) AS c, MAX(date) AS last_date FROM drone_repairs WHERE drone_serial = ?",
        (drone_serial,),
    )
    return await cur.fetchone()


async def get_generator_repairs(generator_serial: str, limit=5):
    conn = await get_conn()
    cur = await conn.execute(
        "SELECT * FROM generator_repairs WHERE generator_serial = ? ORDER BY date DESC, act_number DESC LIMIT ?",
        (generator_serial, limit),
    )
    return await cur.fetchall()


# ---------- drone <-> team / equipment assignment ----------

async def assign_drone_team(drone_serial, team_code):
    conn = await get_conn()
    await conn.execute(
        "UPDATE drones SET team_code = ? WHERE serial = ?", (team_code, drone_serial)
    )
    await conn.commit()


async def unassign_drone_team(drone_serial):
    conn = await get_conn()
    await conn.execute("UPDATE drones SET team_code = NULL WHERE serial = ?", (drone_serial,))
    await conn.commit()


async def list_drones_missing_equipment(team_code):
    """Drones of this team that still need generator, batteries or vehicle filled in."""
    conn = await get_conn()
    cur = await conn.execute("SELECT * FROM drones WHERE team_code = ?", (team_code,))
    drones = await cur.fetchall()
    missing = []
    for d in drones:
        if await drone_missing_equipment(d["serial"]):
            missing.append(d)
    return missing


async def drone_missing_equipment(drone_serial) -> bool:
    drone = await get_drone(drone_serial)
    if not drone:
        return False
    if not drone["generator_serial"] or not drone["vehicle_plate"]:
        return True
    batteries = await get_batteries(drone_serial)
    return len(batteries) < 3


async def set_drone_generator(drone_serial, serial, work_hours, last_oil_change_hours):
    conn = await get_conn()
    drone = await get_drone(drone_serial)
    if drone and drone["generator_serial"] and drone["generator_serial"] != serial:
        await conn.execute(
            "UPDATE generators SET drone_serial = NULL WHERE serial = ?",
            (drone["generator_serial"],),
        )
    await conn.execute(
        "INSERT INTO generators (serial, manufacturer, model, work_hours, "
        "oil_change_interval_hours, last_oil_change_hours, repairs_count, drone_serial) "
        "VALUES (?, 'DJI', NULL, ?, ?, ?, 0, ?) "
        "ON CONFLICT(serial) DO UPDATE SET work_hours=excluded.work_hours, "
        "last_oil_change_hours=excluded.last_oil_change_hours, drone_serial=excluded.drone_serial",
        (serial, work_hours, config.DEFAULT_GENERATOR_OIL_INTERVAL_HOURS, last_oil_change_hours, drone_serial),
    )
    await conn.execute("UPDATE drones SET generator_serial = ? WHERE serial = ?", (serial, drone_serial))
    await conn.commit()


async def replace_batteries_for_drone(drone_serial, batteries):
    """batteries: list of (serial, cycles) tuples, up to 3. Returns the new battery ids."""
    conn = await get_conn()
    await conn.execute("DELETE FROM batteries WHERE drone_serial = ?", (drone_serial,))
    ids = []
    for i, (serial, cycles) in enumerate(batteries, start=1):
        cur = await conn.execute(
            "INSERT INTO batteries (serial, manufacturer, model, cycles, resource_cycles, "
            "drone_serial, slot) VALUES (?, 'DJI', NULL, ?, ?, ?, ?)",
            (serial, cycles, config.DEFAULT_BATTERY_RESOURCE_CYCLES, drone_serial, i),
        )
        ids.append(cur.lastrowid)
    await conn.commit()
    return ids


async def set_drone_vehicle(drone_serial, manufacturer, plate_number, vin, mileage_km, last_oil_change_km):
    conn = await get_conn()
    drone = await get_drone(drone_serial)
    if drone and drone["vehicle_plate"] and drone["vehicle_plate"] != plate_number:
        await conn.execute(
            "UPDATE vehicles SET drone_serial = NULL WHERE plate_number = ?",
            (drone["vehicle_plate"],),
        )
    await conn.execute(
        "INSERT INTO vehicles (plate_number, manufacturer, tech_passport, vin, mileage_km, "
        "oil_change_interval_km, last_oil_change_km, drone_serial) "
        "VALUES (?, ?, NULL, ?, ?, ?, ?, ?) "
        "ON CONFLICT(plate_number) DO UPDATE SET manufacturer=excluded.manufacturer, "
        "vin=excluded.vin, mileage_km=excluded.mileage_km, "
        "last_oil_change_km=excluded.last_oil_change_km, drone_serial=excluded.drone_serial",
        (
            plate_number,
            manufacturer,
            vin,
            mileage_km,
            config.DEFAULT_VEHICLE_OIL_INTERVAL_KM,
            last_oil_change_km,
            drone_serial,
        ),
    )
    await conn.execute("UPDATE drones SET vehicle_plate = ? WHERE serial = ?", (plate_number, drone_serial))
    await conn.commit()


# ---------- notification tier tracking (avoid re-notifying the same status) ----------

async def get_battery_notified_tier(battery_id):
    conn = await get_conn()
    cur = await conn.execute("SELECT last_notified_tier FROM batteries WHERE id = ?", (battery_id,))
    row = await cur.fetchone()
    return row["last_notified_tier"] if row else 0


async def set_battery_notified_tier(battery_id, tier):
    conn = await get_conn()
    await conn.execute("UPDATE batteries SET last_notified_tier = ? WHERE id = ?", (tier, battery_id))
    await conn.commit()


async def get_generator_notified_tier(serial):
    conn = await get_conn()
    cur = await conn.execute("SELECT last_notified_tier FROM generators WHERE serial = ?", (serial,))
    row = await cur.fetchone()
    return row["last_notified_tier"] if row else 0


async def set_generator_notified_tier(serial, tier):
    conn = await get_conn()
    await conn.execute("UPDATE generators SET last_notified_tier = ? WHERE serial = ?", (tier, serial))
    await conn.commit()


async def get_vehicle_notified_tier(plate):
    conn = await get_conn()
    cur = await conn.execute("SELECT last_notified_tier FROM vehicles WHERE plate_number = ?", (plate,))
    row = await cur.fetchone()
    return row["last_notified_tier"] if row else 0


async def set_vehicle_notified_tier(plate, tier):
    conn = await get_conn()
    await conn.execute("UPDATE vehicles SET last_notified_tier = ? WHERE plate_number = ?", (tier, plate))
    await conn.commit()


# ---------- updates (wear readings) ----------

async def update_drone_flight_hours(serial, hours):
    conn = await get_conn()
    await conn.execute("UPDATE drones SET flight_hours = ? WHERE serial = ?", (hours, serial))
    await conn.commit()


async def update_drone_flight_count(serial, count):
    conn = await get_conn()
    await conn.execute("UPDATE drones SET flight_count = ? WHERE serial = ?", (count, serial))
    await conn.commit()


async def update_battery_cycles(battery_id, cycles):
    conn = await get_conn()
    await conn.execute("UPDATE batteries SET cycles = ? WHERE id = ?", (cycles, battery_id))
    await conn.commit()


async def update_generator_hours(serial, work_hours):
    conn = await get_conn()
    await conn.execute("UPDATE generators SET work_hours = ? WHERE serial = ?", (work_hours, serial))
    await conn.commit()


async def reset_generator_oil(serial, at_hours):
    conn = await get_conn()
    await conn.execute(
        "UPDATE generators SET last_oil_change_hours = ? WHERE serial = ?", (at_hours, serial)
    )
    await conn.commit()


async def update_vehicle_mileage(plate, mileage_km):
    conn = await get_conn()
    await conn.execute(
        "UPDATE vehicles SET mileage_km = ? WHERE plate_number = ?", (mileage_km, plate)
    )
    await conn.commit()


async def reset_vehicle_oil(plate, at_km):
    conn = await get_conn()
    await conn.execute(
        "UPDATE vehicles SET last_oil_change_km = ? WHERE plate_number = ?", (at_km, plate)
    )
    await conn.commit()


# ---------- reports ----------

async def create_report(telegram_id, team_code, drone_serial, work_type, location, area, note):
    conn = await get_conn()
    cur = await conn.execute(
        "INSERT INTO reports (telegram_id, team_code, drone_serial, work_type, location, area, "
        "note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            telegram_id,
            team_code,
            drone_serial,
            work_type,
            location,
            area,
            note,
            datetime.utcnow().isoformat(),
        ),
    )
    await conn.commit()
    return cur.lastrowid


async def add_report_media(report_id, file_id, file_type):
    conn = await get_conn()
    await conn.execute(
        "INSERT INTO report_media (report_id, file_id, file_type) VALUES (?, ?, ?)",
        (report_id, file_id, file_type),
    )
    await conn.commit()


async def get_report(report_id):
    conn = await get_conn()
    cur = await conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
    report = await cur.fetchone()
    if not report:
        return None, []
    cur = await conn.execute(
        "SELECT * FROM report_media WHERE report_id = ?", (report_id,)
    )
    media = await cur.fetchall()
    return report, media


async def list_reports(team_code=None, drone_serial=None, limit=8, offset=0):
    conn = await get_conn()
    query = "SELECT * FROM reports WHERE 1=1"
    params = []
    if team_code:
        query += " AND team_code = ?"
        params.append(team_code)
    if drone_serial:
        query += " AND drone_serial = ?"
        params.append(drone_serial)
    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    cur = await conn.execute(query, params)
    return await cur.fetchall()


async def count_reports(team_code=None, drone_serial=None):
    conn = await get_conn()
    query = "SELECT COUNT(*) AS c FROM reports WHERE 1=1"
    params = []
    if team_code:
        query += " AND team_code = ?"
        params.append(team_code)
    if drone_serial:
        query += " AND drone_serial = ?"
        params.append(drone_serial)
    cur = await conn.execute(query, params)
    row = await cur.fetchone()
    return row["c"]


# ---------- wash reports (daily drone-rinse video) ----------

async def create_wash_report(team_code, drone_serial, telegram_id, video_file_id, wash_date):
    conn = await get_conn()
    cur = await conn.execute(
        "INSERT INTO wash_reports (team_code, drone_serial, telegram_id, video_file_id, "
        "wash_date, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (team_code, drone_serial, telegram_id, video_file_id, wash_date, datetime.utcnow().isoformat()),
    )
    await conn.commit()
    return cur.lastrowid


async def get_wash_reports_for_team_date(team_code, wash_date):
    conn = await get_conn()
    cur = await conn.execute(
        "SELECT * FROM wash_reports WHERE team_code = ? AND wash_date = ? ORDER BY created_at",
        (team_code, wash_date),
    )
    return await cur.fetchall()


async def has_washed_today(team_code, wash_date):
    rows = await get_wash_reports_for_team_date(team_code, wash_date)
    return len(rows) > 0


# ---------- full parkwide equipment listings (admin/manager) ----------

async def list_generators(team_code=None):
    conn = await get_conn()
    if team_code:
        cur = await conn.execute(
            "SELECT g.* FROM generators g JOIN drones d ON d.serial = g.drone_serial "
            "WHERE d.team_code = ? ORDER BY g.drone_serial",
            (team_code,),
        )
    else:
        cur = await conn.execute(
            "SELECT * FROM generators WHERE drone_serial IS NOT NULL ORDER BY drone_serial"
        )
    return await cur.fetchall()


async def list_batteries(team_code=None):
    conn = await get_conn()
    if team_code:
        cur = await conn.execute(
            "SELECT b.* FROM batteries b JOIN drones d ON d.serial = b.drone_serial "
            "WHERE d.team_code = ? ORDER BY b.drone_serial, b.slot",
            (team_code,),
        )
    else:
        cur = await conn.execute(
            "SELECT * FROM batteries WHERE drone_serial IS NOT NULL ORDER BY drone_serial, slot"
        )
    return await cur.fetchall()


async def list_vehicles(team_code=None):
    conn = await get_conn()
    if team_code:
        cur = await conn.execute(
            "SELECT v.* FROM vehicles v JOIN drones d ON d.serial = v.drone_serial "
            "WHERE d.team_code = ? ORDER BY v.drone_serial",
            (team_code,),
        )
    else:
        cur = await conn.execute(
            "SELECT * FROM vehicles WHERE drone_serial IS NOT NULL ORDER BY drone_serial"
        )
    return await cur.fetchall()


# ---------- fleet-wide summary ----------

async def fleet_summary():
    conn = await get_conn()
    cur = await conn.execute("SELECT COUNT(*) AS c FROM drones")
    drones_count = (await cur.fetchone())["c"]

    cur = await conn.execute("SELECT model, COUNT(*) AS c FROM drones GROUP BY model")
    by_model = await cur.fetchall()

    cur = await conn.execute("SELECT * FROM batteries")
    batteries = await cur.fetchall()

    cur = await conn.execute("SELECT * FROM generators WHERE drone_serial IS NOT NULL")
    generators = await cur.fetchall()

    cur = await conn.execute("SELECT * FROM vehicles WHERE drone_serial IS NOT NULL")
    vehicles = await cur.fetchall()

    return {
        "drones_count": drones_count,
        "by_model": by_model,
        "batteries": batteries,
        "generators": generators,
        "vehicles": vehicles,
    }


async def reset_test_data(keep_telegram_id=None):
    """Admin-triggered full reset for clearing out test data before going
    live: wipes every registration, team claim, generator/battery/vehicle
    entry, report and wash video, and restores the 17-drone fleet to its
    original Excel-seeded values (manufacturer/model/flight hours) with
    nothing attached. `keep_telegram_id`, if given, is kept in `users` so
    the admin who triggered the reset isn't locked out of their own bot."""
    conn = await get_conn()

    if keep_telegram_id is not None:
        await conn.execute("DELETE FROM users WHERE telegram_id != ?", (keep_telegram_id,))
    else:
        await conn.execute("DELETE FROM users")

    await conn.execute("DELETE FROM batteries")
    await conn.execute("DELETE FROM generators")
    await conn.execute("DELETE FROM vehicles")
    await conn.execute("DELETE FROM reports")
    await conn.execute("DELETE FROM report_media")
    await conn.execute("DELETE FROM wash_reports")
    await conn.execute("DELETE FROM teams")
    await conn.execute(
        "UPDATE drones SET team_code = NULL, vehicle_plate = NULL, generator_serial = NULL"
    )
    await conn.commit()

    if os.path.exists(config.SEED_FILE):
        with open(config.SEED_FILE, encoding="utf-8") as f:
            data = json.load(f)
        for serial, d in data["drones"].items():
            await conn.execute(
                "UPDATE drones SET manufacturer = ?, model = ?, flight_hours = ?, flight_count = ? "
                "WHERE serial = ?",
                (d["manufacturer"], d["model"], d["flight_hours"], d["flight_count"], serial),
            )
        await conn.commit()


async def list_all_admins():
    conn = await get_conn()
    cur = await conn.execute("SELECT * FROM users WHERE role = 'admin'")
    return await cur.fetchall()
