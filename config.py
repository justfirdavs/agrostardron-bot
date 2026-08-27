import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Where the SQLite database file lives. On Railway, point this at a mounted
# volume (e.g. /data/bot.db) so data survives redeploys.
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "data", "bot.db"))

# Optional: comma-separated Telegram numeric user IDs that should always be
# treated as admins, e.g. "123456789,987654321". Not required — the very
# first person to press /start on a fresh bot is made admin automatically.
_admin_ids_raw = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = {int(x) for x in _admin_ids_raw.replace(" ", "").split(",") if x.strip().isdigit()}

# --- Wear/service thresholds ---
DEFAULT_BATTERY_RESOURCE_CYCLES = 800   # average battery life, cycles
BATTERY_WARNING_CYCLES_LEFT = 100       # <= this many cycles left -> warning
GENERATOR_OIL_WARNING_HOURS_LEFT = 20   # <= this many hours left -> warning
VEHICLE_OIL_WARNING_KM_LEFT = 1000      # <= this many km left -> warning
DEFAULT_GENERATOR_OIL_INTERVAL_HOURS = 50    # how often generator oil is changed
DEFAULT_VEHICLE_OIL_INTERVAL_KM = 10000      # how often vehicle oil is changed

COMPANY_NAME = "АгроСтарДрон"

SEED_FILE = os.path.join(os.path.dirname(__file__), "data", "seed_data.json")
