"""All database access lives here: schema, seeding from the Excel-derived
JSON fixture, and query helpers used by the handlers."""
import json
import os
from datetime import datetime

import aiosqlite

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    code TEXT PRIMARY KEY
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
    slot INTEGER
);

CREATE TABLE IF NOT EXISTS generators (
    serial TEXT PRIMARY KEY,
    manufacturer TEXT,
    model TEXT,
    work_hours REAL,
    oil_change_interval_hours REAL DEFAULT 50,
    last_oil_change_hours REAL,
    repairs_count INTEGER DEFAULT 0,
    drone_serial TEXT
);

CREATE TABLE IF NOT EXISTS vehicles (
    plate_number TEXT PRIMARY KEY,
    manufacturer TEXT,
    tech_passport TEXT,
    vin TEXT,
    mileage_km REAL,
    oil_change_interval_km REAL DEFAULT 10000,
    last_oil_change_km REAL,
    drone_serial TEXT
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
    await seed_if_empty()


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


async def create_user(telegram_id, full_name, username, role, team_code=None, is_leader=0):
    conn = await get_conn()
    await conn.execute(
        "INSERT OR REPLACE INTO users (telegram_id, full_name, username, role, team_code, "
        "is_leader, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (telegram_id, full_name, username, role, team_code, int(is_leader), datetime.utcnow().isoformat()),
    )
    await conn.commit()


async def set_user_role(telegram_id, role):
    conn = await get_conn()
    await conn.execute("UPDATE users SET role = ? WHERE telegram_id = ?", (role, telegram_id))
    await conn.commit()


async def list_team_members(team_code):
    conn = await get_conn()
    cur = await conn.execute(
        "SELECT * FROM users WHERE team_code = ? ORDER BY is_leader DESC, full_name",
        (team_code,),
    )
    return await cur.fetchall()


async def get_team_leader(team_code):
    conn = await get_conn()
    cur = await conn.execute(
        "SELECT * FROM users WHERE team_code = ? AND is_leader = 1 LIMIT 1", (team_code,)
    )
    return await cur.fetchone()


async def is_leader_of_drone(telegram_id, drone_serial):
    user = await get_user(telegram_id)
    if not user or not user["is_leader"] or user["role"] != "team":
        return False
    drone = await get_drone(drone_serial)
    return bool(drone and drone["team_code"] == user["team_code"])


# ---------- teams ----------

async def get_team(code: str):
    conn = await get_conn()
    cur = await conn.execute("SELECT * FROM teams WHERE code = ?", (code,))
    return await cur.fetchone()


async def list_teams():
    conn = await get_conn()
    cur = await conn.execute("SELECT * FROM teams ORDER BY code")
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
    """batteries: list of (serial, cycles) tuples, up to 3."""
    conn = await get_conn()
    await conn.execute("DELETE FROM batteries WHERE drone_serial = ?", (drone_serial,))
    for i, (serial, cycles) in enumerate(batteries, start=1):
        await conn.execute(
            "INSERT INTO batteries (serial, manufacturer, model, cycles, resource_cycles, "
            "drone_serial, slot) VALUES (?, 'DJI', NULL, ?, ?, ?, ?)",
            (serial, cycles, config.DEFAULT_BATTERY_RESOURCE_CYCLES, drone_serial, i),
        )
    await conn.commit()


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


async def list_all_admins():
    conn = await get_conn()
    cur = await conn.execute("SELECT * FROM users WHERE role = 'admin'")
    return await cur.fetchall()
