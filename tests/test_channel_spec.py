import json
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from telebot import types


class ChannelShopSpecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(
            "os.environ",
            {
                "TELEGRAM_BOT_TOKEN": "unit-test-token",
                "ADMIN_IDS": "1",
                "CHANNEL_ID": "@test_channel",
                "AUTO_DELETE_OUT_OF_STOCK_DAYS": "7",
            },
        ):
            from shopbot import channel, db
            from shopbot.channel import (
                format_channel_caption,
                format_product_code,
                order_button_markup,
            )
            from shopbot.i18n import translate
            from shopbot.keyboards import (
                admin_product_actions_keyboard,
                admin_product_preview_keyboard,
                category_pagination_keyboard,
                out_of_stock_keyboard,
                product_keyboard,
            )

        cls.db = db
        cls.channel = channel
        cls.format_channel_caption = staticmethod(format_channel_caption)
        cls.format_product_code = staticmethod(format_product_code)
        cls.order_button_markup = staticmethod(order_button_markup)
        cls.translate = staticmethod(translate)
        cls.product_keyboard = staticmethod(product_keyboard)
        cls.out_of_stock_keyboard = staticmethod(out_of_stock_keyboard)
        cls.category_pagination_keyboard = staticmethod(category_pagination_keyboard)
        cls.admin_product_actions_keyboard = staticmethod(admin_product_actions_keyboard)
        cls.admin_product_preview_keyboard = staticmethod(admin_product_preview_keyboard)

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = patch.object(
            self.db,
            "DB_PATH",
            Path(self.temp_dir.name) / "shop.sqlite3",
        )
        self.database_path.start()
        self.db.initialize_database()

    def tearDown(self):
        self.database_path.stop()
        self.temp_dir.cleanup()

    def test_database_schema_and_columns(self):
        with self.db.database() as conn:
            prod_cols = {
                r["name"] for r in conn.execute("PRAGMA table_info(products)").fetchall()
            }
            expected_cols = {
                "id",
                "category_id",
                "name",
                "description",
                "price",
                "photo_file_id",
                "is_available",
                "out_of_stock_at",
                "channel_message_ids",
                "created_at",
                "updated_at",
            }
            self.assertTrue(expected_cols.issubset(prod_cols))

            photo_cols = {
                r["name"]
                for r in conn.execute("PRAGMA table_info(product_photos)").fetchall()
            }
            self.assertEqual(photo_cols, {"id", "product_id", "file_id", "position"})

    def test_product_photos_helpers(self):
        with self.db.database() as conn:
            conn.execute("INSERT INTO categories (name) VALUES ('Cat 1')")
            cursor = conn.execute(
                "INSERT INTO products (category_id, name, price) VALUES (1, 'Item 1', '100')"
            )
            prod_id = cursor.lastrowid
            self.db.set_product_photos(conn, prod_id, ["photo_1", "photo_2", "photo_3"])

            photos = self.db.get_product_photos(conn, prod_id)
            self.assertEqual(photos, ["photo_1", "photo_2", "photo_3"])

    def test_format_product_code(self):
        self.assertEqual(self.format_product_code(42), "#P0042")
        self.assertEqual(self.format_product_code(1), "#P0001")
        self.assertEqual(self.format_product_code(1234), "#P1234")

    def test_format_channel_caption_in_stock_and_out_of_stock(self):
        in_stock_caption = self.format_channel_caption(
            name="Пуховик зимний",
            product_id=42,
            description="Тёплый зимний пуховик",
            price="890000",
            is_available=True,
        )
        self.assertIn("Пуховик зимний", in_stock_caption)
        self.assertIn("#P0042", in_stock_caption)
        self.assertNotIn("НЕТ В НАЛИЧИИ", in_stock_caption)

        out_stock_caption = self.format_channel_caption(
            name="Пуховик зимний",
            product_id=42,
            description="Тёплый зимний пуховик",
            price="890000",
            is_available=False,
        )
        self.assertIn("НЕТ В НАЛИЧИИ", out_stock_caption)
        self.assertIn("#P0042", out_stock_caption)

    def test_order_button_markup_url(self):
        markup = self.order_button_markup("my_test_bot", 42)
        button = markup.keyboard[0][0]
        self.assertEqual(button.text, "🛒 Заказать")
        self.assertEqual(button.url, "https://t.me/my_test_bot?start=order_42")

    def test_deep_link_id_and_direct_search_regex(self):
        # Deep link parameter extraction
        param = "order_42"
        match = re.search(r"\d+", param)
        self.assertIsNotNone(match)
        self.assertEqual(int(match.group(0)), 42)

        param2 = "order_P0042"
        match2 = re.search(r"\d+", param2)
        self.assertIsNotNone(match2)
        self.assertEqual(int(match2.group(0)), 42)

        # Direct search parsing regex: 42, #42, #P0042, P42
        test_inputs = ["42", "#42", "#P0042", "P42", "#p42", "p0042"]
        id_pattern = re.compile(r"^#?[pP]?0*(\d+)$")
        for inp in test_inputs:
            m = id_pattern.match(inp)
            self.assertIsNotNone(m, f"Failed on input: {inp}")
            self.assertEqual(int(m.group(1)), 42)

    def test_product_keyboard_contains_cart_and_buy_now(self):
        keyboard = self.product_keyboard(1, 42, is_available=True)
        row = keyboard.keyboard[0]
        callbacks = [btn.callback_data for btn in row]
        self.assertIn("cart:add:42", callbacks)
        self.assertIn("cart:buynow:42", callbacks)

    def test_cleanup_channel_cron_logic(self):
        from scripts.cleanup_channel import cleanup_out_of_stock_posts

        mock_bot = MagicMock()
        with self.db.database() as conn:
            conn.execute("INSERT INTO categories (name) VALUES ('Cat 1')")
            # 1. Out of stock 10 days ago with published post
            old_dt = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
            conn.execute(
                """
                INSERT INTO products (category_id, name, price, is_available, out_of_stock_at, channel_message_ids)
                VALUES (1, 'Old Out Item', '100', 0, ?, ?)
                """,
                (old_dt, json.dumps([101, 102])),
            )
            # 2. Out of stock 2 days ago (< 7 days)
            recent_dt = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
            conn.execute(
                """
                INSERT INTO products (category_id, name, price, is_available, out_of_stock_at, channel_message_ids)
                VALUES (1, 'Recent Out Item', '200', 0, ?, ?)
                """,
                (recent_dt, json.dumps([201])),
            )
            # 3. In stock item
            conn.execute(
                """
                INSERT INTO products (category_id, name, price, is_available, channel_message_ids)
                VALUES (1, 'In Stock Item', '300', 1, ?)
                """,
                (json.dumps([301]),),
            )

        cleaned = cleanup_out_of_stock_posts(bot=mock_bot)
        self.assertEqual(cleaned, 1)
        mock_bot.delete_message.assert_any_call(chat_id="@test_channel", message_id=101)
        mock_bot.delete_message.assert_any_call(chat_id="@test_channel", message_id=102)

        # Check DB state
        with self.db.database() as conn:
            old_prod = conn.execute(
                "SELECT channel_message_ids FROM products WHERE name = 'Old Out Item'"
            ).fetchone()
            self.assertIsNone(old_prod["channel_message_ids"])

            recent_prod = conn.execute(
                "SELECT channel_message_ids FROM products WHERE name = 'Recent Out Item'"
            ).fetchone()
            self.assertIsNotNone(recent_prod["channel_message_ids"])

    def test_locales_completeness(self):
        import json

        locales_file = (
            Path(__file__).resolve().parent.parent / "shopbot" / "locales.json"
        )
        with open(locales_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        required_keys = [
            "buy_now",
            "out_of_stock_message",
            "view_other_products",
            "page_prev",
            "page_next",
            "all_categories",
            "photo_received_counter",
            "btn_done",
            "btn_publish_channel",
            "btn_save_bot",
            "btn_edit",
            "btn_cancel",
            "btn_unpublish_channel",
            "btn_delete_full",
            "avail_in_stock",
            "avail_out_of_stock",
            "status_available_toggle",
            "confirm_delete_product",
            "btn_confirm_delete",
            "product_published_channel",
            "product_unpublished_channel",
            "product_preview_header",
            "select_category_or_create",
            "category_new_button",
        ]

        for lang in ("ru", "uz", "en"):
            for key in required_keys:
                self.assertIn(
                    key,
                    data[lang],
                    f"Missing key '{key}' in language '{lang}'",
                )


if __name__ == "__main__":
    unittest.main()
