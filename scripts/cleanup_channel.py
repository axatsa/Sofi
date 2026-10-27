"""Cron script for cleaning up out-of-stock product posts from Telegram channel.

Deletes posts for products that have been out of stock for more than
AUTO_DELETE_OUT_OF_STOCK_DAYS (default: 7 days).

Usage:
    python scripts/cleanup_channel.py
"""

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import telebot
from telebot.apihelper import ApiTelegramException

from shopbot.config import AUTO_DELETE_OUT_OF_STOCK_DAYS, CHANNEL_ID, TOKEN, logger
from shopbot.db import database, initialize_database


def cleanup_out_of_stock_posts(bot: telebot.TeleBot | None = None) -> int:
    if not CHANNEL_ID:
        logger.info("CHANNEL_ID not set. Skipping channel cleanup.")
        return 0

    if bot is None:
        bot = telebot.TeleBot(TOKEN)

    initialize_database()
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=AUTO_DELETE_OUT_OF_STOCK_DAYS)

    with database() as connection:
        rows = connection.execute(
            """
            SELECT id, name, channel_message_ids, out_of_stock_at
            FROM products
            WHERE is_available = 0
              AND channel_message_ids IS NOT NULL
              AND channel_message_ids != ''
              AND out_of_stock_at IS NOT NULL
            """
        ).fetchall()

    cleaned_count = 0
    for row in rows:
        out_time_str = row["out_of_stock_at"]
        try:
            out_dt = datetime.fromisoformat(out_time_str)
            if out_dt.tzinfo is None:
                out_dt = out_dt.replace(tzinfo=timezone.utc)
            if out_dt > cutoff_dt:
                continue
        except (ValueError, TypeError):
            pass

        try:
            msg_ids = json.loads(row["channel_message_ids"])
        except Exception:
            msg_ids = []

        logger.info(
            "Deleting channel post for out-of-stock product #%s (%s), message IDs: %s",
            row["id"],
            row["name"],
            msg_ids,
        )

        for msg_id in msg_ids:
            try:
                bot.delete_message(chat_id=CHANNEL_ID, message_id=msg_id)
            except ApiTelegramException as e:
                logger.debug(
                    "Message %s could not be deleted (might be already deleted): %s",
                    msg_id,
                    e,
                )

        with database() as connection:
            connection.execute(
                "UPDATE products SET channel_message_ids = NULL WHERE id = ?",
                (row["id"],),
            )
        cleaned_count += 1

    logger.info("Channel cleanup finished. Cleaned %d products.", cleaned_count)
    return cleaned_count


def main():
    cleaned = cleanup_out_of_stock_posts()
    print(f"Cleanup complete. Deleted channel posts for {cleaned} out-of-stock product(s).")


if __name__ == "__main__":
    main()
