"""Populate shop database with demo categories, products and real photos.

Products and prices are inspired by the Just (just2010.uz) clothing store
in Uzbekistan.  Photos come from Unsplash for reliable downloads.

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

DEMO_CATEGORIES = [
    "🧥 Верхняя одежда",
    "👕 Футболки и поло",
    "🧶 Худи и свитшоты",
    "👔 Рубашки",
    "👖 Джинсы и брюки",
    "🧣 Свитеры и кардиганы",
    "👟 Обувь",
    "🎒 Сумки и аксессуары",
]

# ---------------------------------------------------------------------------
# ~30 products inspired by Just (just2010.uz) catalog with Unsplash photos
# ---------------------------------------------------------------------------
DEMO_PRODUCTS = [
    # ── 🧥 Верхняя одежда (5) ────────────────────────────────────────────
    {
        "category": "🧥 Верхняя одежда",
        "name": "Куртка стёганая",
        "description": "Стёганая демисезонная куртка, водоотталкивающая ткань, молния YKK",
        "price": "489900",
        "image_urls": [
            "https://images.unsplash.com/photo-1544923246-77307dd654cb?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "🧥 Верхняя одежда",
        "name": "Ветровка с капюшоном",
        "description": "Лёгкая ветровка из нейлона с регулируемым капюшоном, унисекс",
        "price": "349900",
        "image_urls": [
            "https://images.unsplash.com/photo-1548883354-7622d03aca27?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "🧥 Верхняя одежда",
        "name": "Жилетка утеплённая",
        "description": "Утеплённая жилетка на синтепоне, стоячий воротник",
        "price": "299900",
        "image_urls": [
            "https://images.unsplash.com/photo-1591047139829-d91aecb6caea?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "🧥 Верхняя одежда",
        "name": "Пальто классическое",
        "description": "Мужское пальто из шерстяной ткани, приталенный силуэт",
        "price": "699900",
        "image_urls": [
            "https://images.unsplash.com/photo-1539533113208-f6df8cc8b543?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "🧥 Верхняя одежда",
        "name": "Анорак",
        "description": "Спортивный анорак с карманом-кенгуру, ветрозащитный",
        "price": "379900",
        "image_urls": [
            "https://images.unsplash.com/photo-1551028719-00167b16eac5?auto=format&fit=crop&w=800&q=80",
        ],
    },
    # ── 👕 Футболки и поло (4) ───────────────────────────────────────────
    {
        "category": "👕 Футболки и поло",
        "name": "Футболка оверсайз",
        "description": "Хлопковая футболка свободного кроя, плотность 220 г/м²",
        "price": "129900",
        "image_urls": [
            "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "👕 Футболки и поло",
        "name": "Футболка с принтом",
        "description": "Стильная футболка с графическим принтом, 100% хлопок",
        "price": "149900",
        "image_urls": [
            "https://images.unsplash.com/photo-1503341455253-b2e723bb3dbb?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "👕 Футболки и поло",
        "name": "Поло классическое",
        "description": "Мужское поло с воротником, хлопок-пике, вышитый логотип",
        "price": "189900",
        "image_urls": [
            "https://images.unsplash.com/photo-1586363104862-3a5e2ab60d99?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "👕 Футболки и поло",
        "name": "Футболка базовая",
        "description": "Базовая однотонная футболка, удлинённый крой, чёрная",
        "price": "99900",
        "image_urls": [
            "https://images.unsplash.com/photo-1583743814966-8936f5b7be1a?auto=format&fit=crop&w=800&q=80",
        ],
    },
    # ── 🧶 Худи и свитшоты (4) ──────────────────────────────────────────
    {
        "category": "🧶 Худи и свитшоты",
        "name": "Худи с капюшоном",
        "description": "Худи из французского трикотажа, флисовая подкладка",
        "price": "279900",
        "image_urls": [
            "https://images.unsplash.com/photo-1556905055-8f358a7a47b2?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "🧶 Худи и свитшоты",
        "name": "Свитшот базовый",
        "description": "Базовый свитшот без капюшона, рибана на манжетах",
        "price": "229900",
        "image_urls": [
            "https://images.unsplash.com/photo-1578768079470-0a4536cc5f77?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "🧶 Худи и свитшоты",
        "name": "Худи на молнии",
        "description": "Спортивное худи на молнии, два боковых кармана",
        "price": "299900",
        "image_urls": [
            "https://images.unsplash.com/photo-1620799140408-edc6dcb6d633?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "🧶 Худи и свитшоты",
        "name": "Свитшот с принтом",
        "description": "Свитшот с авторским принтом, oversize крой",
        "price": "249900",
        "image_urls": [
            "https://images.unsplash.com/photo-1614495039893-f3d6c930f212?auto=format&fit=crop&w=800&q=80",
        ],
    },
    # ── 👔 Рубашки (3) ──────────────────────────────────────────────────
    {
        "category": "👔 Рубашки",
        "name": "Рубашка льняная",
        "description": "Лёгкая рубашка из натурального льна, свободный крой",
        "price": "269900",
        "image_urls": [
            "https://images.unsplash.com/photo-1598033129183-c4f50c736f10?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "👔 Рубашки",
        "name": "Рубашка в клетку",
        "description": "Фланелевая рубашка в клетку, утеплённая, кнопки",
        "price": "249900",
        "image_urls": [
            "https://images.unsplash.com/photo-1596755094514-f87e34085b2c?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "👔 Рубашки",
        "name": "Рубашка оксфорд",
        "description": "Классическая рубашка Oxford, button-down воротник, белая",
        "price": "289900",
        "image_urls": [
            "https://images.unsplash.com/photo-1603252109303-2751441dd157?auto=format&fit=crop&w=800&q=80",
        ],
    },
    # ── 👖 Джинсы и брюки (5) ───────────────────────────────────────────
    {
        "category": "👖 Джинсы и брюки",
        "name": "Джинсы прямые",
        "description": "Классические прямые джинсы, синий деним, 100% хлопок",
        "price": "349900",
        "image_urls": [
            "https://images.unsplash.com/photo-1541099649105-f69ad21f3246?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "👖 Джинсы и брюки",
        "name": "Джинсы slim fit",
        "description": "Зауженные джинсы с эластаном, тёмно-серые",
        "price": "379900",
        "image_urls": [
            "https://images.unsplash.com/photo-1542272604-787c3835535d?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "👖 Джинсы и брюки",
        "name": "Брюки чинос",
        "description": "Брюки чинос из хлопка с эластаном, бежевые",
        "price": "289900",
        "image_urls": [
            "https://images.unsplash.com/photo-1473966968600-fa801b869a1a?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "👖 Джинсы и брюки",
        "name": "Джоггеры",
        "description": "Спортивные джоггеры из трикотажа, манжеты на резинке",
        "price": "219900",
        "image_urls": [
            "https://images.unsplash.com/photo-1552902865-b72c031ac5ea?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "👖 Джинсы и брюки",
        "name": "Шорты карго",
        "description": "Шорты карго с накладными карманами, хлопок",
        "price": "179900",
        "image_urls": [
            "https://images.unsplash.com/photo-1591195853828-11db59a44f6b?auto=format&fit=crop&w=800&q=80",
        ],
    },
    # ── 🧣 Свитеры и кардиганы (3) ──────────────────────────────────────
    {
        "category": "🧣 Свитеры и кардиганы",
        "name": "Свитер с горлом",
        "description": "Мужской свитер с высоким горлом, шерсть-акрил",
        "price": "329900",
        "image_urls": [
            "https://images.unsplash.com/photo-1638032776698-b1fd05bd9b84?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "🧣 Свитеры и кардиганы",
        "name": "Кардиган вязаный",
        "description": "Кардиган крупной вязки на пуговицах, oversize",
        "price": "359900",
        "image_urls": [
            "https://images.unsplash.com/photo-1434389677669-e08b4cda3a20?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "🧣 Свитеры и кардиганы",
        "name": "Джемпер хлопковый",
        "description": "Лёгкий джемпер из мерсеризованного хлопка, V-горловина",
        "price": "269900",
        "image_urls": [
            "https://images.unsplash.com/photo-1614975059251-992f11792571?auto=format&fit=crop&w=800&q=80",
        ],
    },
    # ── 👟 Обувь (4) ────────────────────────────────────────────────────
    {
        "category": "👟 Обувь",
        "name": "Кроссовки спортивные",
        "description": "Лёгкие кроссовки с дышащей сеткой, EVA подошва",
        "price": "449900",
        "image_urls": [
            "https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "👟 Обувь",
        "name": "Кеды классические",
        "description": "Белые кеды из плотного хлопка, резиновая подошва",
        "price": "249900",
        "image_urls": [
            "https://images.unsplash.com/photo-1525966222134-fcfa99b8ae77?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "👟 Обувь",
        "name": "Лоферы замшевые",
        "description": "Замшевые лоферы, кожаная стелька, бежевые",
        "price": "529900",
        "image_urls": [
            "https://images.unsplash.com/photo-1614252369475-531eba835eb1?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "👟 Обувь",
        "name": "Ботинки челси",
        "description": "Кожаные ботинки челси, эластичные вставки, осень-весна",
        "price": "589900",
        "image_urls": [
            "https://images.unsplash.com/photo-1638247025967-b4e38f787b76?auto=format&fit=crop&w=800&q=80",
        ],
    },
    # ── 🎒 Сумки и аксессуары (3) ───────────────────────────────────────
    {
        "category": "🎒 Сумки и аксессуары",
        "name": "Рюкзак городской",
        "description": "Городской рюкзак с отделением для ноутбука 15.6\", водонепроницаемый",
        "price": "329900",
        "image_urls": [
            "https://images.unsplash.com/photo-1553062407-98eeb64c6a62?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "🎒 Сумки и аксессуары",
        "name": "Сумка через плечо",
        "description": "Компактная сумка через плечо, экокожа, чёрная",
        "price": "189900",
        "image_urls": [
            "https://images.unsplash.com/photo-1548036328-c9fa89d128fa?auto=format&fit=crop&w=800&q=80",
        ],
    },
    {
        "category": "🎒 Сумки и аксессуары",
        "name": "Ремень кожаный",
        "description": "Ремень из натуральной кожи, металлическая пряжка, коричневый",
        "price": "149900",
        "image_urls": [
            "https://images.unsplash.com/photo-1624222247344-550fb60583dc?auto=format&fit=crop&w=800&q=80",
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

        total = len(DEMO_PRODUCTS)
        for idx, item in enumerate(DEMO_PRODUCTS, 1):
            cat_name = item["category"]
            prod_name = item["name"]
            desc = item["description"]
            price = item["price"]
            cat_id = categories.get(cat_name)

            if cat_id is None:
                print(f"  ⚠️ Категория «{cat_name}» не найдена, пропуск")
                continue

            existing = conn.execute(
                "SELECT id, photo_file_id FROM products WHERE name = ? AND category_id = ?",
                (prod_name, cat_id),
            ).fetchone()

            if existing:
                product_id = existing["id"]
                print(f"  🔄 [{idx}/{total}] Обновление товара #{product_id}: {prod_name}")
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO products (category_id, name, description, price, is_available)
                    VALUES (?, ?, ?, ?, 1)
                    """,
                    (cat_id, prod_name, desc, price),
                )
                product_id = cursor.lastrowid
                print(f"  ✅ [{idx}/{total}] Создан товар #{product_id}: {prod_name} — {price} UZS")

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

    print(f"\n🎉 Автосидинг с фото успешно завершен! ({total} товаров)")


if __name__ == "__main__":
    seed_with_images()
