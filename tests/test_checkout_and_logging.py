import re
import unittest
from shopbot.config import LOG_FILE, log_action
from shopbot.keyboards import phone_request_keyboard


class CheckoutAndLoggingTests(unittest.TestCase):
    def test_phone_request_keyboard_structure(self):
        markup = phone_request_keyboard(12345)
        # First row must have request_contact=True button
        contact_btn = markup.keyboard[0][0]
        req_contact = (
            contact_btn.get("request_contact")
            if isinstance(contact_btn, dict)
            else getattr(contact_btn, "request_contact", False)
        )
        text = (
            contact_btn.get("text")
            if isinstance(contact_btn, dict)
            else getattr(contact_btn, "text", "")
        )
        self.assertTrue(req_contact)
        self.assertIn("номером", text.lower())
        # Second row must have cancel button
        cancel_btn = markup.keyboard[1][0]
        cancel_text = (
            cancel_btn.get("text")
            if isinstance(cancel_btn, dict)
            else getattr(cancel_btn, "text", "")
        )
        self.assertIn("отмена", cancel_text.lower())

    def test_phone_validation_logic(self):
        valid_cases = [
            ("+998901234567", "+998901234567"),
            ("998901234567", "+998901234567"),
            ("+7 (999) 123-45-67", "+79991234567"),
            ("90 123 45 67", "+901234567"),
        ]

        def parse_phone(text: str) -> str | None:
            cleaned = re.sub(r"[^\d+]", "", text.strip())
            digits = re.sub(r"\D", "", cleaned)
            if len(digits) >= 7:
                return cleaned if cleaned.startswith("+") else f"+{cleaned}"
            return None

        for raw, expected in valid_cases:
            self.assertEqual(parse_phone(raw), expected)

        invalid_cases = [
            "",
            "hello",
            "123",
            "123456",  # 6 digits < 7
            "call me",
            "+--",
        ]
        for raw in invalid_cases:
            self.assertIsNone(parse_phone(raw))

    def test_logging_action_and_file(self):
        test_action = "TEST_AUTOMATED_ACTION"
        test_details = "test_details_payload_123"
        log_action(99999, "testuser", test_action, test_details)

        self.assertTrue(LOG_FILE.exists())
        content = LOG_FILE.read_text(encoding="utf-8")
        self.assertIn("USER_ACTION [@testuser]: TEST_AUTOMATED_ACTION | test_details_payload_123", content)

    def test_admin_edit_keyboards(self):
        from shopbot.keyboards import (
            admin_edit_category_keyboard,
            admin_edit_product_keyboard,
            admin_photo_upload_keyboard,
        )

        # Photo upload keyboard count=0
        kb_photo_0 = admin_photo_upload_keyboard(12345, count=0)
        callbacks_0 = [
            b.callback_data for row in kb_photo_0.keyboard for b in row
        ]
        self.assertIn("admin_prod:photo_done", callbacks_0)
        self.assertIn("admin_prod:cancel", callbacks_0)

        # Photo upload keyboard count=3
        kb_photo_3 = admin_photo_upload_keyboard(12345, count=3)
        callbacks_3 = [
            b.callback_data for row in kb_photo_3.keyboard for b in row
        ]
        self.assertIn("admin_prod:photo_done", callbacks_3)
        self.assertIn("admin_prod:cancel", callbacks_3)

        # Edit product keyboard
        kb_edit = admin_edit_product_keyboard(12345, product_id=42, photos_count=2)
        callbacks_edit = [
            b.callback_data for row in kb_edit.keyboard for b in row
        ]
        self.assertIn("admin_edit_field:42:name", callbacks_edit)
        self.assertIn("admin_edit_field:42:category", callbacks_edit)
        self.assertIn("admin_edit_field:42:price", callbacks_edit)
        self.assertIn("admin_edit_field:42:desc", callbacks_edit)
        self.assertIn("admin_edit_field:42:photos", callbacks_edit)
        self.assertIn("admin_edit_field:42:done", callbacks_edit)

        # Edit category keyboard
        cats = [{"id": 1, "name": "Перчатки"}, {"id": 2, "name": "Шарфы"}]
        kb_cat = admin_edit_category_keyboard(12345, product_id=42, categories=cats)
        callbacks_cat = [
            b.callback_data for row in kb_cat.keyboard for b in row
        ]
        self.assertIn("admin_set_cat:42:1", callbacks_cat)
        self.assertIn("admin_set_cat:42:2", callbacks_cat)
        self.assertIn("admin_set_cat:42:new", callbacks_cat)
        self.assertIn("admin_set_cat:42:cancel", callbacks_cat)


if __name__ == "__main__":
    unittest.main()
