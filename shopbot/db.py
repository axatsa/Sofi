import sqlite3
from contextlib import contextmanager

from .config import DB_PATH

LANGUAGES = {"ru", "uz", "en"}


@contextmanager
def database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    # SQLite отключает внешние ключи по умолчанию; иначе удаление товара могло бы
    # оставить в корзинах покупателей ссылки на уже несуществующую запись.
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database():
    with database() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE
            );
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                price TEXT NOT NULL,
                photo_file_id TEXT,
                is_available INTEGER NOT NULL DEFAULT 1,
                out_of_stock_at TEXT,
                channel_message_ids TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS product_photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                file_id TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_product_photos_product_id ON product_photos(product_id);
            CREATE TABLE IF NOT EXISTS cart_items (
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                PRIMARY KEY (user_id, product_id)
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                customer_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                address TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                total TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                product_name TEXT NOT NULL,
                unit_price TEXT NOT NULL,
                quantity INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                language TEXT NOT NULL CHECK (language IN ('ru', 'uz', 'en'))
            );
            """
        )

        # Migrations for existing databases
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(products)").fetchall()
        }
        if "is_available" not in columns:
            connection.execute(
                "ALTER TABLE products ADD COLUMN is_available INTEGER NOT NULL DEFAULT 1"
            )
        if "out_of_stock_at" not in columns:
            connection.execute(
                "ALTER TABLE products ADD COLUMN out_of_stock_at TEXT"
            )
        if "channel_message_ids" not in columns:
            connection.execute(
                "ALTER TABLE products ADD COLUMN channel_message_ids TEXT"
            )
        if "created_at" not in columns:
            connection.execute(
                "ALTER TABLE products ADD COLUMN created_at TEXT"
            )
            connection.execute(
                "UPDATE products SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"
            )
        if "updated_at" not in columns:
            connection.execute(
                "ALTER TABLE products ADD COLUMN updated_at TEXT"
            )
            connection.execute(
                "UPDATE products SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL"
            )

        # Migrate legacy photo_file_id to product_photos
        if "photo_file_id" in columns:
            legacy_products = connection.execute(
                """
                SELECT id, photo_file_id FROM products
                WHERE photo_file_id IS NOT NULL AND photo_file_id != ''
                """
            ).fetchall()
            for prod in legacy_products:
                has_photos = connection.execute(
                    "SELECT 1 FROM product_photos WHERE product_id = ? LIMIT 1",
                    (prod["id"],),
                ).fetchone()
                if not has_photos:
                    connection.execute(
                        "INSERT INTO product_photos (product_id, file_id, position) VALUES (?, ?, 0)",
                        (prod["id"], prod["photo_file_id"]),
                    )


def get_product_photos(connection: sqlite3.Connection, product_id: int) -> list[str]:
    rows = connection.execute(
        "SELECT file_id FROM product_photos WHERE product_id = ? ORDER BY position, id",
        (product_id,),
    ).fetchall()
    return [row["file_id"] for row in rows]


def set_product_photos(connection: sqlite3.Connection, product_id: int, file_ids: list[str]):
    connection.execute("DELETE FROM product_photos WHERE product_id = ?", (product_id,))
    for pos, file_id in enumerate(file_ids):
        connection.execute(
            "INSERT INTO product_photos (product_id, file_id, position) VALUES (?, ?, ?)",
            (product_id, file_id, pos),
        )
    # Also update legacy photo_file_id for backwards compatibility
    primary_photo = file_ids[0] if file_ids else None
    connection.execute(
        "UPDATE products SET photo_file_id = ? WHERE id = ?",
        (primary_photo, product_id),
    )


def get_language(user_id: int) -> str:
    with database() as connection:
        row = connection.execute(
            "SELECT language FROM user_settings WHERE user_id = ?", (user_id,)
        ).fetchone()
    return row["language"] if row else "ru"


def set_language(user_id: int, language: str):
    if language not in LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    with database() as connection:
        connection.execute(
            """
            INSERT INTO user_settings (user_id, language) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET language = excluded.language
            """,
            (user_id, language),
        )
