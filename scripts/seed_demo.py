"""Populate the shop database with demo categories and products.

Usage:
    python scripts/seed_demo.py
"""

import sqlite3
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shopbot.config import DB_PATH
from shopbot.db import initialize_database

DEMO_CATEGORIES = ["🧥 Верхняя одежда", "👕 Повседневная", "👟 Обувь"]

DEMO_PRODUCTS = [
    # (category, name, description, price)
    ("🧥 Верхняя одежда", "Пуховик", "Тёплый зимний пуховик, водоотталкивающая ткань", "890000"),
    ("🧥 Верхняя одежда", "Тренч", "Классический тренч бежевого цвета, хлопок", "750000"),
    ("🧥 Верхняя одежда", "Кожаная куртка", "Куртка из натуральной кожи, чёрная", "1200000"),
    ("🧥 Верхняя одежда", "Ветровка", "Лёгкая ветровка с капюшоном, унисекс", "320000"),
    ("👕 Повседневная", "Футболка оверсайз", "Хлопковая футболка свободного кроя, белая", "150000"),
    ("👕 Повседневная", "Худи", "Худи с капюшоном, флисовая подкладка", "280000"),
    ("👕 Повседневная", "Джинсы прямые", "Классические прямые джинсы, синий деним", "350000"),
    ("👕 Повседневная", "Рубашка льняная", "Лёгкая рубашка из натурального льна", "270000"),
    ("👟 Обувь", "Кроссовки", "Спортивные кроссовки, дышащая сетка", "450000"),
    ("👟 Обувь", "Ботинки челси", "Кожаные ботинки челси, осень-весна", "680000"),
    ("👟 Обувь", "Кеды", "Классические белые кеды, хлопковый верх", "250000"),
    ("👟 Обувь", "Лоферы", "Замшевые лоферы, бежевые", "520000"),
]


def seed():
    initialize_database()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")

        for name in DEMO_CATEGORIES:
            try:
                conn.execute("INSERT INTO categories (name) VALUES (?)", (name,))
                print(f"  ✅ Категория: {name}")
            except sqlite3.IntegrityError:
                print(f"  ⏭  Категория уже есть: {name}")

        categories = {
            row["name"]: row["id"]
            for row in conn.execute("SELECT id, name FROM categories").fetchall()
        }

        for cat_name, prod_name, description, price in DEMO_PRODUCTS:
            cat_id = categories.get(cat_name)
            if cat_id is None:
                print(f"  ⚠️  Категория «{cat_name}» не найдена, пропускаю {prod_name}")
                continue
            existing = conn.execute(
                "SELECT id FROM products WHERE name = ? AND category_id = ?",
                (prod_name, cat_id),
            ).fetchone()
            if existing:
                print(f"  ⏭  Товар уже есть: {prod_name}")
                continue
            conn.execute(
                """
                INSERT INTO products (category_id, name, description, price, is_available)
                VALUES (?, ?, ?, ?, 1)
                """,
                (cat_id, prod_name, description, price),
            )
            print(f"  ✅ Товар: {prod_name} — {price} UZS")

        conn.commit()
    print("\n🎉 Демо-данные загружены! Запускай бота: python bot.py")


if __name__ == "__main__":
    seed()
