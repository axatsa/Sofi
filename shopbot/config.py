import logging
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_IDS = {
    int(value.strip())
    for value in os.getenv("ADMIN_IDS", "").split(",")
    if value.strip().isdigit()
}
DB_PATH = Path(os.getenv("DATABASE_PATH", str(BASE_DIR / "shop.sqlite3")))
CURRENCY = os.getenv("CURRENCY", "UZS").strip() or "UZS"
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()
try:
    AUTO_DELETE_OUT_OF_STOCK_DAYS = int(os.getenv("AUTO_DELETE_OUT_OF_STOCK_DAYS", "7"))
except ValueError:
    AUTO_DELETE_OUT_OF_STOCK_DAYS = 7

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("tg_shop")

if not TOKEN:
    raise RuntimeError("Set TELEGRAM_BOT_TOKEN in the .env file before starting the bot.")
if not ADMIN_IDS:
    raise RuntimeError("Set at least one numeric Telegram user ID in ADMIN_IDS in the .env file.")
