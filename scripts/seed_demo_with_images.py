"""Populate shop database with demo categories, products and real photos.

Fetches high quality clothes photos from Unsplash, uploads them to Telegram
to get permanent file_id references, stores in product_photos, and
publishes to the configured Telegram channel (if CHANNEL_ID is set).

Usage:
    python scripts/seed_demo_with_images.py
"""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
import telebot
from telebot.apihelper import ApiTelegramException

from shopbot.channel import publish_product_to_channel
from shopbot.config import ADMIN_IDS, CHANNEL_ID, DB_PATH, TOKEN
from shopbot.db import initialize_database, set_product_photos

DEMO_CATEGORIES = ["🧥 Верхняя одежда", "👕 Повседневная", "👟 Обувь"]

DEMO_PRODUCTS = [
    {
        "category": "🧥 Верхняя одежда",
        "name": "Пуховик",
        "description": "Тёплый зимний пуховик, водоотталкивающая ткань",
        "price": "890000",
        "image_urls": [
            "https://images.unsplash.com/photo-1544923246-77307dd654cb?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "🧥 Верхняя одежда",
        "name": "Тренч",
        "description": "Классический тренч бежевого цвета, хлопок",
        "price": "750000",
        "image_urls": [
            "https://images.unsplash.com/photo-1591047139829-d91aecb6caea?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "🧥 Верхняя одежда",
        "name": "Кожаная куртка",
        "description": "Куртка из натуральной кожи, чёрная",
        "price": "1200000",
        "image_urls": [
            "https://images.unsplash.com/photo-1551028719-00167b16eac5?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "🧥 Верхняя одежда",
        "name": "Ветровка",
        "description": "Лёгкая ветровка с капюшоном, унисекс",
        "price": "320000",
        "image_urls": [
            "https://images.unsplash.com/photo-1548883354-7622d03aca27?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "👕 Повседневная",
        "name": "Футболка оверсайз",
        "description": "Хлопковая футболка свободного кроя, белая",
        "price": "150000",
        "image_urls": [
            "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "👕 Повседневная",
        "name": "Худи",
        "description": "Худи с капюшоном, флисовая подкладка",
        "price": "280000",
        "image_urls": [
            "https://images.unsplash.com/photo-1556905055-8f358a7a47b2?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "👕 Повседневная",
        "name": "Джинсы прямые",
        "description": "Классические прямые джинсы, синий деним",
        "price": "350000",
        "image_urls": [
            "https://images.unsplash.com/photo-1541099649105-f69ad21f3246?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "👕 Повседневная",
        "name": "Рубашка льняная",
        "description": "Лёгкая рубашка из натурального льна",
        "price": "270000",
        "image_urls": [
            "https://images.unsplash.com/photo-1598033129183-c4f50c736f10?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "👟 Обувь",
        "name": "Кроссовки",
        "description": "Спортивные кроссовки, дышащая сетка",
        "price": "450000",
        "image_urls": [
            "https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "👟 Обувь",
        "name": "Ботинки челси",
        "description": "Кожаные ботинки челси, осень-весна",
        "price": "680000",
        "image_urls": [
            "https://images.unsplash.com/photo-1638247025967-b4e38f787b76?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "👟 Обувь",
        "name": "Кеды",
        "description": "Классические белые кеды, хлопковый верх",
        "price": "250000",
        "image_urls": [
            "https://images.unsplash.com/photo-1525966222134-fcfa99b8ae77?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "👟 Обувь",
        "name": "Лоферы",
        "description": "Замшевые лоферы, бежевые",
        "price": "520000",
        "image_urls": [
            "https://images.unsplash.com/photo-1614252369475-531eba835eb1?auto=format&fit=crop&w=800&q=80",
        ],
    },
]


def download_image_to_temp(url: str) -> str | None:
    try:
        resp = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
        )
        if resp.status_code == 200 and resp.content:
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            tmp.write(resp.content)
            tmp.flush()
            tmp.close()
            return tmp.name
    except Exception as e:
        print(f"    ⚠️ Не удалось загрузить фото ({e})")
    return None


def upload_photo_to_telegram(bot: telebot.TeleBot, photo_path: str) -> str | None:
    target_chat = CHANNEL_ID if CHANNEL_ID else (next(iter(ADMIN_IDS)) if ADMIN_IDS else None)
    if not target_chat:
        return None

    try:
        with open(photo_path, "rb") as f:
            msg = bot.send_photo(target_chat, f)
            file_id = msg.photo[-1].file_id
            if target_chat == CHANNEL_ID:
                try:
                    bot.delete_message(target_chat, msg.message_id)
                except Exception:
                    pass
            return file_id
    except ApiTelegramException as e:
        if target_chat == CHANNEL_ID and ADMIN_IDS:
            admin_target = next(iter(ADMIN_IDS))
            try:
                with open(photo_path, "rb") as f:
                    msg = bot.send_photo(admin_target, f)
                    return msg.photo[-1].file_id
            except Exception as e2:
                print(f"    ⚠️ Ошибка отправки фото в Telegram: {e2}")
        else:
            print(f"    ⚠️ Ошибка отправки фото в Telegram: {e}")
    return None


def seed_with_images():
    initialize_database()
    bot = telebot.TeleBot(TOKEN)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")

        for name in DEMO_CATEGORIES:
            try:
                conn.execute("INSERT INTO categories (name) VALUES (?)", (name,))
                print(f"  ✅ Категория: {name}")
            except sqlite3.IntegrityError:
                print(f"  ⏭  Категория уже существует: {name}")

        categories = {
            row["name"]: row["id"]
            for row in conn.execute("SELECT id, name FROM categories").fetchall()
        }

        for item in DEMO_PRODUCTS:
            cat_name = item["category"]
            prod_name = item["name"]
            desc = item["description"]
            price = item["price"]
            cat_id = categories.get(cat_name)

            if cat_id is None:
                continue

            existing = conn.execute(
                "SELECT id, photo_file_id FROM products WHERE name = ? AND category_id = ?",
                (prod_name, cat_id),
            ).fetchone()

            if existing:
                product_id = existing["id"]
                print(f"  🔄 Обновление товара #{product_id}: {prod_name}")
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO products (category_id, name, description, price, is_available)
                    VALUES (?, ?, ?, ?, 1)
                    """,
                    (cat_id, prod_name, desc, price),
                )
                product_id = cursor.lastrowid
                print(f"  ✅ Создан товар #{product_id}: {prod_name} — {price} UZS")

            photos_rows = conn.execute(
                "SELECT file_id FROM product_photos WHERE product_id = ?",
                (product_id,),
            ).fetchall()

            file_ids = [r["file_id"] for r in photos_rows]

            if not file_ids:
                print(f"    📥 Загрузка фото для «{prod_name}»...")
                for url in item.get("image_urls", []):
                    tmp_file = download_image_to_temp(url)
                    if tmp_file:
                        try:
                            file_id = upload_photo_to_telegram(bot, tmp_file)
                            if file_id:
                                file_ids.append(file_id)
                                print(f"    ✨ Получен Telegram file_id: {file_id[:16]}...")
                        finally:
                            if os.path.exists(tmp_file):
                                os.remove(tmp_file)

                if file_ids:
                    set_product_photos(conn, product_id, file_ids)
                    conn.commit()

            if CHANNEL_ID:
                try:
                    pub = publish_product_to_channel(bot, product_id)
                    if pub:
                        print(f"    📢 Опубликовано в канал {CHANNEL_ID}: msg_ids={pub}")
                except Exception as e:
                    print(f"    ⚠️ Не удалось опубликовать в канал: {e}")

        conn.commit()

    print("\n🎉 Автосидинг с фото успешно завершен!")


if __name__ == "__main__":
    seed_with_images()
