import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

class LanguageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(
            "os.environ",
            {"TELEGRAM_BOT_TOKEN": "unit-test-token", "ADMIN_IDS": "1"},
        ):
            from shopbot import common
            from shopbot import db
            from shopbot.i18n import _language_for_user, set_language, translate
            from shopbot.keyboards import admin_menu_keyboard, customer_menu_keyboard

        cls.common = common
        cls.db = db
        cls.admin_menu_keyboard = staticmethod(admin_menu_keyboard)
        cls.customer_menu_keyboard = staticmethod(customer_menu_keyboard)
        cls.language_cache = _language_for_user
        cls.set_language = staticmethod(set_language)
        cls.translate = staticmethod(translate)

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = patch.object(
            self.db,
            "DB_PATH",
            Path(self.temp_dir.name) / "shop.sqlite3",
        )
        self.database_path.start()
        self.db.initialize_database()
        self.language_cache.cache_clear()

    def tearDown(self):
        self.language_cache.cache_clear()
        self.database_path.stop()
        self.temp_dir.cleanup()

    def test_language_choice_is_saved_and_loaded_after_cache_clear(self):
        self.set_language(42, "uz")
        self.assertEqual(
            self.translate(42, "language_saved"),
            "Til o‘zbekchaga o‘zgartirildi.",
        )

        self.language_cache.cache_clear()

        self.assertEqual(
            self.translate(42, "language_saved"),
            "Til o‘zbekchaga o‘zgartirildi.",
        )
        self.assertEqual(self.db.get_language(42), "uz")

    def test_unsupported_language_is_rejected(self):
        with self.assertRaises(ValueError):
            self.set_language(42, "fr")

        self.assertEqual(self.db.get_language(42), "ru")

    def test_language_menu_labels_are_translated(self):
        expected_labels = {
            "ru": "🇷🇺 Русский",
            "uz": "🇷🇺 Ruscha",
            "en": "🇷🇺 Russian",
        }
        for language, label in expected_labels.items():
            self.set_language(42, language)
            self.assertEqual(self.translate(42, "language_option_ru"), label)

    def test_admin_password_requires_allowlisted_user_and_matching_password(self):
        with (
            patch.object(self.common, "ADMIN_IDS", {1}),
            patch.object(self.common, "ADMIN_PASSWORD", "long-test-password"),
        ):
            self.assertTrue(
                self.common.verify_admin_password(1, "long-test-password")
            )
            self.assertFalse(self.common.verify_admin_password(1, "wrong-password"))
            self.assertFalse(
                self.common.verify_admin_password(2, "long-test-password")
            )

    def test_admin_command_access_requires_authenticated_session(self):
        from shopbot.state import authenticated_admin

        with patch.object(self.common, "ADMIN_IDS", {1}):
            authenticated_admin.discard(1)
            self.assertFalse(self.common.is_authenticated_admin(1))
            authenticated_admin.add(1)
            self.assertTrue(self.common.is_authenticated_admin(1))
            self.assertFalse(self.common.is_authenticated_admin(2))
            authenticated_admin.discard(1)

    def test_customer_and_admin_menus_expose_their_expected_buttons(self):
        customer_buttons = {
            button["text"]
            for row in self.customer_menu_keyboard().keyboard
            for button in row
        }
        admin_buttons = {
            button["text"]
            for row in self.admin_menu_keyboard().keyboard
            for button in row
        }

        self.assertTrue(
            {"🛒 Магазин", "🔍 Поиск", "🧺 Корзина", "🔐 Админ"}
            <= customer_buttons
        )
        self.assertTrue(
            {
                "➕ Категория",
                "➕ Товар",
                "📑 Заказы",
                "📝 Статус заказа",
                "🚪 Выход",
            }
            <= admin_buttons
        )


if __name__ == "__main__":
    unittest.main()
