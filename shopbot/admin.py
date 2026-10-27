import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from html import escape
from telebot import types

from .channel import (
    delete_product_from_channel,
    format_channel_caption,
    publish_product_to_channel,
    update_channel_post,
)
from .common import is_authenticated_admin, money, parse_price
from .config import CURRENCY, log_action, logger
from .db import database, get_product_photos, set_product_photos
from .i18n import translate
from .keyboards import (
    admin_delete_confirm_keyboard,
    admin_edit_category_keyboard,
    admin_edit_product_keyboard,
    admin_photo_upload_keyboard,
    admin_product_actions_keyboard,
    admin_product_preview_keyboard,
    admin_select_category_keyboard,
)


def register_admin_handlers(bot, pending_admin):
    def admin_required(message) -> bool:
        if not is_authenticated_admin(message.from_user.id):
            log_action(message.from_user.id, message.from_user.username, "ADMIN_UNAUTHORIZED_ACCESS", message.text or "")
            bot.reply_to(message, translate(message.from_user.id, "admin_required"))
            return False
        return True

    def begin_menu_flow(message, mode, prompt_key):
        pending_admin[message.from_user.id] = {"mode": mode, "step": "input"}
        bot.reply_to(message, translate(message.from_user.id, prompt_key))

    @bot.message_handler(commands=["add_category"])
    def add_category(message):
        if not admin_required(message):
            return
        name = message.text.partition(" ")[2].strip()
        if not name:
            begin_menu_flow(message, "add_category", "category_add_prompt")
            return
        try:
            with database() as connection:
                connection.execute("INSERT INTO categories (name) VALUES (?)", (name,))
            log_action(message.from_user.id, message.from_user.username, "ADMIN_ADD_CATEGORY", name)
            bot.reply_to(
                message,
                translate(message.from_user.id, "category_created", name=name),
            )
        except sqlite3.IntegrityError:
            bot.reply_to(message, translate(message.from_user.id, "category_exists"))

    @bot.message_handler(commands=["categories"])
    def list_categories(message):
        if not admin_required(message):
            return
        log_action(message.from_user.id, message.from_user.username, "ADMIN_LIST_CATEGORIES")
        with database() as connection:
            rows = connection.execute(
                "SELECT id, name FROM categories ORDER BY name"
            ).fetchall()
        bot.reply_to(
            message,
            "\n".join(
                translate(
                    message.from_user.id,
                    "category_list_item",
                    id=row["id"],
                    name=row["name"],
                )
                for row in rows
            )
            if rows
            else translate(message.from_user.id, "no_categories"),
        )

    @bot.message_handler(commands=["delete_category"])
    def delete_category(message):
        if not admin_required(message):
            return
        if len(message.text.split()) == 1:
            begin_menu_flow(message, "delete_category", "category_delete_prompt")
            return
        try:
            category_id = int(message.text.split()[1])
            with database() as connection:
                result = connection.execute(
                    "DELETE FROM categories WHERE id = ?", (category_id,)
                )
            key = "category_deleted" if result.rowcount else "category_not_found"
            log_action(message.from_user.id, message.from_user.username, "ADMIN_DELETE_CATEGORY", f"id={category_id}, deleted={bool(result.rowcount)}")
            bot.reply_to(message, translate(message.from_user.id, key))
        except (IndexError, ValueError):
            bot.reply_to(
                message,
                translate(message.from_user.id, "category_delete_usage"),
            )
        except sqlite3.IntegrityError:
            bot.reply_to(message, translate(message.from_user.id, "category_has_products"))

    @bot.message_handler(commands=["rename_category"])
    def rename_category(message):
        if not admin_required(message):
            return
        parts = message.text.split(maxsplit=2)
        if len(parts) != 3:
            if len(parts) == 1:
                pending_admin[message.from_user.id] = {
                    "mode": "rename_category",
                    "step": "id",
                }
                bot.reply_to(
                    message,
                    translate(message.from_user.id, "category_rename_id_prompt"),
                )
                return
            bot.reply_to(
                message,
                translate(message.from_user.id, "rename_category_usage"),
            )
            return
        try:
            category_id = int(parts[1])
            new_name = parts[2].strip()
            with database() as connection:
                result = connection.execute(
                    "UPDATE categories SET name = ? WHERE id = ?",
                    (new_name, category_id),
                )
            key = "category_renamed" if result.rowcount else "category_not_found"
            log_action(message.from_user.id, message.from_user.username, "ADMIN_RENAME_CATEGORY", f"id={category_id}, new_name={new_name}")
            bot.reply_to(message, translate(message.from_user.id, key))
        except ValueError:
            bot.reply_to(message, translate(message.from_user.id, "category_id_invalid"))
        except sqlite3.IntegrityError:
            bot.reply_to(message, translate(message.from_user.id, "category_exists"))

    def show_product_edit_card(chat_id: int, user_id: int, product_id: int):
        with database() as connection:
            product = connection.execute(
                """
                SELECT p.*, c.name AS category_name
                FROM products p JOIN categories c ON c.id = p.category_id
                WHERE p.id = ?
                """,
                (product_id,),
            ).fetchone()
            if not product:
                bot.send_message(chat_id, translate(user_id, "product_not_found"))
                return
            photos = get_product_photos(connection, product_id)

        code = f"#P{product['id']:04d}"
        channel_status = (
            "📢 Опубликован в канале"
            if product["channel_message_ids"]
            else "📱 Только в боте"
        )
        caption = translate(
            user_id,
            "edit_card_header",
            id=code,
            name=escape(product["name"]),
            category=escape(product["category_name"] or "-"),
            price=money(product["price"]),
            description=escape(product["description"] or "—"),
            photo_count=len(photos),
            channel_status=channel_status,
        )
        markup = admin_edit_product_keyboard(user_id, product_id, len(photos))

        if photos:
            bot.send_photo(
                chat_id,
                photos[0],
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup,
            )
        else:
            bot.send_message(
                chat_id,
                caption,
                parse_mode="HTML",
                reply_markup=markup,
            )

    def begin_product_flow(chat_id: int, user_id: int, product=None):
        if product:
            show_product_edit_card(chat_id, user_id, product["id"])
            return

        pending_admin[user_id] = {
            "mode": "add",
            "product_id": None,
            "values": {
                "name": None,
                "category": None,
                "description": "",
                "price": None,
                "photos": [],
            },
            "step": "name",
        }
        bot.send_message(chat_id, translate(user_id, "product_name_prompt_new"))

    @bot.message_handler(commands=["add_product"])
    def add_product(message):
        if admin_required(message):
            begin_product_flow(message.chat.id, message.from_user.id)

    @bot.message_handler(commands=["edit_product"])
    def edit_product(message):
        if not admin_required(message):
            return
        if len(message.text.split()) == 1:
            begin_menu_flow(message, "edit_product", "product_edit_id_prompt")
            return
        try:
            product_id = int(message.text.split()[1])
        except (IndexError, ValueError):
            bot.reply_to(message, translate(message.from_user.id, "edit_product_usage"))
            return
        show_product_edit_card(message.chat.id, message.from_user.id, product_id)

    @bot.message_handler(commands=["products"])
    def list_products(message):
        if not admin_required(message):
            return
        user_id = message.from_user.id
        with database() as connection:
            rows = connection.execute(
                """
                SELECT p.id, p.name, p.price, p.is_available, p.channel_message_ids,
                       p.description, c.name AS category
                FROM products p JOIN categories c ON c.id = p.category_id
                ORDER BY p.id
                """
            ).fetchall()
        if not rows:
            bot.reply_to(message, translate(user_id, "no_products"))
            return

        for row in rows:
            with database() as conn:
                photos = get_product_photos(conn, row["id"])
            status_text = (
                translate(user_id, "avail_in_stock")
                if row["is_available"]
                else translate(user_id, "avail_out_of_stock")
            )
            has_channel = bool(row["channel_message_ids"])
            channel_badge = "📢 В канале" if has_channel else "📱 Только в боте"
            text = (
                f"<b>{escape(row['name'])}</b> (#{row['id']})\n"
                f"Категория: {escape(row['category'])}\n"
                f"Цена: <b>{money(row['price'])}</b>\n"
                f"Статус: {status_text} | {channel_badge}"
            )
            markup = admin_product_actions_keyboard(
                user_id,
                row["id"],
                bool(row["is_available"]),
                has_channel,
            )
            if photos:
                bot.send_photo(
                    message.chat.id,
                    photos[0],
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
            else:
                bot.send_message(
                    message.chat.id,
                    text,
                    parse_mode="HTML",
                    reply_markup=markup,
                )

    @bot.message_handler(commands=["delete_product"])
    def delete_product(message):
        if not admin_required(message):
            return
        if len(message.text.split()) == 1:
            begin_menu_flow(message, "delete_product", "product_delete_prompt")
            return
        try:
            product_id = int(message.text.split()[1])
        except (IndexError, ValueError):
            bot.reply_to(
                message,
                translate(message.from_user.id, "delete_product_usage"),
            )
            return
        delete_product_from_channel(bot, product_id)
        with database() as connection:
            result = connection.execute(
                "DELETE FROM products WHERE id = ?", (product_id,)
            )
        key = "product_deleted" if result.rowcount else "product_not_found"
        log_action(message.from_user.id, message.from_user.username, "ADMIN_DELETE_PRODUCT", f"id={product_id}, deleted={bool(result.rowcount)}")
        bot.reply_to(message, translate(message.from_user.id, key))

    @bot.message_handler(commands=["orders"])
    def list_orders(message):
        if not admin_required(message):
            return
        log_action(message.from_user.id, message.from_user.username, "ADMIN_LIST_ORDERS")
        with database() as connection:
            orders = connection.execute(
                "SELECT * FROM orders ORDER BY id DESC LIMIT 20"
            ).fetchall()
            items_by_order = {order["id"]: [] for order in orders}
            if orders:
                order_ids = tuple(items_by_order)
                placeholders = ", ".join("?" for _ in order_ids)
                items = connection.execute(
                    f"""
                    SELECT order_id, product_name, unit_price, quantity
                    FROM order_items
                    WHERE order_id IN ({placeholders})
                    ORDER BY order_id, id
                    """,
                    order_ids,
                ).fetchall()
                for item in items:
                    items_by_order[item["order_id"]].append(item)
        if not orders:
            bot.reply_to(message, translate(message.from_user.id, "orders_empty"))
            return
        for order in orders:
            user_id = message.from_user.id
            lines = [
                translate(
                    user_id,
                    "admin_order",
                    id=order["id"],
                    status=escape(
                        translate(user_id, f"status_{order['status']}")
                    ),
                    name=escape(order["customer_name"]),
                    phone=escape(order["phone"]),
                    address=escape(order["address"]),
                )
            ]
            lines.extend(
                translate(
                    user_id,
                    "order_item",
                    name=escape(item["product_name"]),
                    quantity=item["quantity"],
                    price=money(Decimal(item["unit_price"]) * item["quantity"]),
                )
                for item in items_by_order[order["id"]]
            )
            lines.append(
                translate(
                    user_id,
                    "order_total",
                    total=money(order["total"]),
                )
            )
            bot.send_message(message.chat.id, "\n".join(lines), parse_mode="HTML")

    @bot.message_handler(commands=["set_order_status"])
    def set_order_status(message):
        if not admin_required(message):
            return
        parts = message.text.split()
        if len(parts) == 1:
            begin_menu_flow(message, "set_order_status", "order_id_prompt")
            return
        allowed = {"new", "processing", "completed", "cancelled"}
        if len(parts) != 3 or parts[2].lower() not in allowed:
            bot.reply_to(
                message,
                translate(message.from_user.id, "order_status_usage"),
            )
            return
        try:
            order_id = int(parts[1])
        except ValueError:
            bot.reply_to(message, translate(message.from_user.id, "order_id_invalid"))
            return
        with database() as connection:
            result = connection.execute(
                "UPDATE orders SET status = ? WHERE id = ?",
                (parts[2].lower(), order_id),
            )
        key = "order_status_updated" if result.rowcount else "order_not_found"
        log_action(message.from_user.id, message.from_user.username, "ADMIN_SET_ORDER_STATUS", f"id={order_id}, status={parts[2].lower()}")
        bot.reply_to(message, translate(message.from_user.id, key))

    def show_product_preview(chat_id: int, user_id: int, state: dict):
        values = state["values"]
        state["step"] = "preview"
        photos = values.get("photos", [])
        caption = format_channel_caption(
            name=values["name"],
            product_id=state.get("product_id") or 0,
            description=values.get("description", ""),
            price=values["price"],
            is_available=True,
        )
        preview_markup = admin_product_preview_keyboard(user_id)

        if len(photos) == 1:
            bot.send_photo(
                chat_id,
                photos[0],
                caption=caption,
                parse_mode="HTML",
                reply_markup=preview_markup,
            )
        elif len(photos) > 1:
            media = [
                types.InputMediaPhoto(photos[0], caption=caption, parse_mode="HTML")
            ]
            for p in photos[1:5]:
                media.append(types.InputMediaPhoto(p))
            bot.send_media_group(chat_id, media)
            bot.send_message(
                chat_id,
                translate(user_id, "product_preview_header"),
                parse_mode="HTML",
                reply_markup=preview_markup,
            )
        else:
            bot.send_message(
                chat_id,
                caption,
                parse_mode="HTML",
                reply_markup=preview_markup,
            )

    def finish_product_save(chat_id: int, user_id: int, state: dict, publish: bool):
        values = state["values"]
        with database() as connection:
            category = connection.execute(
                "SELECT id FROM categories WHERE name = ? COLLATE NOCASE",
                (values["category"],),
            ).fetchone()
            if category is None:
                cursor = connection.execute(
                    "INSERT INTO categories (name) VALUES (?)", (values["category"],)
                )
                category_id = cursor.lastrowid
            else:
                category_id = category["id"]

            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            if state["mode"] == "add":
                cursor = connection.execute(
                    """
                    INSERT INTO products
                        (category_id, name, description, price, is_available, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        category_id,
                        values["name"],
                        values["description"],
                        values["price"],
                        now_str,
                        now_str,
                    ),
                )
                product_id = cursor.lastrowid
                response_key = "product_created"
            else:
                product_id = state["product_id"]
                connection.execute(
                    """
                    UPDATE products
                    SET category_id = ?, name = ?, description = ?, price = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        category_id,
                        values["name"],
                        values["description"],
                        values["price"],
                        now_str,
                        product_id,
                    ),
                )
                response_key = "product_updated"

            set_product_photos(connection, product_id, values.get("photos", []))

        pending_admin.pop(user_id, None)
        log_action(
            user_id,
            None,
            "ADMIN_FINISH_PRODUCT_SAVE",
            f"mode={state['mode']}, product_id={product_id}, name={values['name']}, price={values['price']}, photos={len(values.get('photos', []))}, publish={publish}",
        )
        bot.send_message(chat_id, translate(user_id, response_key))

        if publish:
            pub_result = publish_product_to_channel(bot, product_id)
            if pub_result:
                bot.send_message(
                    chat_id, translate(user_id, "product_published_channel")
                )

    def handle_field_edit_input(message, state):
        user_id = message.from_user.id
        username = message.from_user.username
        mode = state["mode"]
        product_id = state["product_id"]

        if message.content_type == "text" and (
            message.text in ("/cancel", translate(user_id, "btn_cancel"), "❌ Отмена")
        ):
            pending_admin.pop(user_id, None)
            log_action(user_id, username, "ADMIN_EDIT_CANCELLED", f"id={product_id}")
            bot.reply_to(message, translate(user_id, "cancelled"))
            show_product_edit_card(message.chat.id, user_id, product_id)
            return

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        if mode == "edit_single_field":
            field = state["field"]
            raw_text = (message.text or "").strip()

            if field == "name":
                if not raw_text or raw_text.startswith("/"):
                    bot.reply_to(message, translate(user_id, "send_product_name"))
                    return
                with database() as connection:
                    connection.execute(
                        "UPDATE products SET name = ?, updated_at = ? WHERE id = ?",
                        (raw_text, now_str, product_id),
                    )
                update_channel_post(bot, product_id)
                pending_admin.pop(user_id, None)
                log_action(user_id, username, "ADMIN_UPDATE_NAME", f"id={product_id}, name={raw_text}")
                bot.reply_to(
                    message,
                    translate(user_id, "field_updated_name", value=raw_text),
                    parse_mode="HTML",
                )
                show_product_edit_card(message.chat.id, user_id, product_id)
                return

            if field == "price":
                price = parse_price(raw_text)
                if price is None:
                    bot.reply_to(message, translate(user_id, "price_invalid"))
                    return
                with database() as connection:
                    connection.execute(
                        "UPDATE products SET price = ?, updated_at = ? WHERE id = ?",
                        (price, now_str, product_id),
                    )
                update_channel_post(bot, product_id)
                pending_admin.pop(user_id, None)
                log_action(user_id, username, "ADMIN_UPDATE_PRICE", f"id={product_id}, price={price}")
                bot.reply_to(
                    message,
                    translate(user_id, "field_updated_price", value=money(price)),
                    parse_mode="HTML",
                )
                show_product_edit_card(message.chat.id, user_id, product_id)
                return

            if field == "desc":
                new_desc = "" if raw_text in ("-", "/clear", "/skip") else raw_text
                with database() as connection:
                    connection.execute(
                        "UPDATE products SET description = ?, updated_at = ? WHERE id = ?",
                        (new_desc, now_str, product_id),
                    )
                update_channel_post(bot, product_id)
                pending_admin.pop(user_id, None)
                log_action(user_id, username, "ADMIN_UPDATE_DESC", f"id={product_id}")
                bot.reply_to(
                    message,
                    translate(user_id, "field_updated_desc"),
                    parse_mode="HTML",
                )
                show_product_edit_card(message.chat.id, user_id, product_id)
                return

        if mode == "edit_category_new":
            raw_text = (message.text or "").strip()
            if not raw_text or raw_text.startswith("/"):
                bot.reply_to(message, translate(user_id, "category_add_prompt"))
                return
            with database() as connection:
                try:
                    cursor = connection.execute(
                        "INSERT INTO categories (name) VALUES (?)", (raw_text,)
                    )
                    cat_id = cursor.lastrowid
                except sqlite3.IntegrityError:
                    cat = connection.execute(
                        "SELECT id FROM categories WHERE name = ?", (raw_text,)
                    ).fetchone()
                    cat_id = cat["id"]
                connection.execute(
                    "UPDATE products SET category_id = ?, updated_at = ? WHERE id = ?",
                    (cat_id, now_str, product_id),
                )
            update_channel_post(bot, product_id)
            pending_admin.pop(user_id, None)
            log_action(user_id, username, "ADMIN_UPDATE_CATEGORY_NEW", f"id={product_id}, cat={raw_text}")
            bot.reply_to(
                message,
                translate(user_id, "field_updated_category", value=raw_text),
                parse_mode="HTML",
            )
            show_product_edit_card(message.chat.id, user_id, product_id)
            return

        if mode == "edit_photos":
            cur_photos = state.setdefault("photos", [])
            if message.content_type == "photo":
                file_id = message.photo[-1].file_id
                if file_id not in cur_photos:
                    cur_photos.append(file_id)
                count = len(cur_photos)
                if count >= 5:
                    with database() as connection:
                        set_product_photos(connection, product_id, cur_photos)
                    update_channel_post(bot, product_id)
                    pending_admin.pop(user_id, None)
                    log_action(user_id, username, "ADMIN_UPDATE_PHOTOS", f"id={product_id}, count={count}")
                    bot.reply_to(
                        message,
                        translate(user_id, "field_updated_photos", count=count),
                    )
                    show_product_edit_card(message.chat.id, user_id, product_id)
                else:
                    bot.reply_to(
                        message,
                        translate(user_id, "photo_received_counter", count=count),
                        reply_markup=admin_photo_upload_keyboard(user_id, count, allow_skip=False),
                    )
                return

            if message.text in ("/skip", "/done"):
                if cur_photos:
                    with database() as connection:
                        set_product_photos(connection, product_id, cur_photos)
                    update_channel_post(bot, product_id)
                    bot.reply_to(
                        message,
                        translate(user_id, "field_updated_photos", count=len(cur_photos)),
                    )
                pending_admin.pop(user_id, None)
                show_product_edit_card(message.chat.id, user_id, product_id)
                return

            bot.reply_to(
                message,
                translate(user_id, "photo_invalid"),
                reply_markup=admin_photo_upload_keyboard(user_id, len(cur_photos), allow_skip=False),
            )
            return

    @bot.message_handler(
        content_types=["text", "photo"],
        func=lambda message: message.from_user.id in pending_admin,
    )
    def handle_admin_input(message):
        user_id = message.from_user.id
        if not is_authenticated_admin(user_id):
            pending_admin.pop(user_id, None)
            return
        state = pending_admin[user_id]
        if state["mode"] in ("edit_single_field", "edit_category_new", "edit_photos"):
            handle_field_edit_input(message, state)
            return

        if state["mode"] != "add":
            handle_menu_input(message, state)
            return

        step = state["step"]

        if step == "name":
            if not message.text or (
                message.text.startswith("/") and message.text != "/skip"
            ):
                bot.reply_to(message, translate(user_id, "send_product_name"))
                return
            if message.text != "/skip" or not state["values"]["name"]:
                state["values"]["name"] = message.text.strip()
            state["step"] = "category"
            with database() as connection:
                categories = connection.execute(
                    "SELECT id, name FROM categories ORDER BY name"
                ).fetchall()
            bot.reply_to(
                message,
                translate(user_id, "select_category_or_create"),
                reply_markup=admin_select_category_keyboard(user_id, categories),
            )

        elif step == "category":
            if state.get("awaiting_new_category"):
                if not message.text or message.text.startswith("/"):
                    bot.reply_to(message, translate(user_id, "category_add_prompt"))
                    return
                cat_name = message.text.strip()
                try:
                    with database() as connection:
                        connection.execute(
                            "INSERT INTO categories (name) VALUES (?)", (cat_name,)
                        )
                except sqlite3.IntegrityError:
                    pass
                state["values"]["category"] = cat_name
                state.pop("awaiting_new_category", None)
            else:
                if message.text == "/skip" and state["values"]["category"]:
                    pass
                elif message.text and not message.text.startswith("/"):
                    state["values"]["category"] = message.text.strip()
                else:
                    with database() as connection:
                        categories = connection.execute(
                            "SELECT id, name FROM categories ORDER BY name"
                        ).fetchall()
                    bot.reply_to(
                        message,
                        translate(user_id, "select_category_or_create"),
                        reply_markup=admin_select_category_keyboard(user_id, categories),
                    )
                    return

            state["step"] = "description"
            bot.reply_to(
                message,
                translate(
                    user_id,
                    "description_prompt",
                    current=state["values"]["description"] or "-",
                ),
            )

        elif step == "description":
            if message.text == "/skip" and state["mode"] == "edit":
                pass
            else:
                state["values"]["description"] = (
                    message.text.strip()
                    if message.text and message.text != "/skip"
                    else ""
                )
            state["step"] = "price"
            bot.reply_to(
                message,
                translate(
                    user_id,
                    "price_prompt",
                    currency=CURRENCY,
                    current=state["values"]["price"] or "-",
                ),
            )

        elif step == "price":
            if message.text == "/skip" and state["mode"] == "edit":
                pass
            else:
                price = parse_price(message.text or "")
                if price is None:
                    bot.reply_to(message, translate(user_id, "price_invalid"))
                    return
                state["values"]["price"] = price

            state["step"] = "photo"
            cur_photos = state["values"].get("photos", [])
            bot.reply_to(
                message,
                translate(user_id, "photo_prompt"),
                reply_markup=admin_photo_upload_keyboard(user_id, len(cur_photos)),
            )

        elif step == "photo":
            cur_photos = state["values"].setdefault("photos", [])
            if message.content_type == "photo":
                file_id = message.photo[-1].file_id
                if file_id not in cur_photos:
                    cur_photos.append(file_id)
                count = len(cur_photos)
                if count >= 5:
                    show_product_preview(message.chat.id, user_id, state)
                else:
                    bot.reply_to(
                        message,
                        translate(user_id, "photo_received_counter", count=count),
                        reply_markup=admin_photo_upload_keyboard(user_id, count),
                    )
            elif message.text in ("/skip", "/done"):
                show_product_preview(message.chat.id, user_id, state)
            else:
                bot.reply_to(
                    message,
                    translate(user_id, "photo_invalid"),
                    reply_markup=admin_photo_upload_keyboard(user_id, len(cur_photos)),
                )

    def handle_menu_input(message, state):
        user_id = message.from_user.id
        username = message.from_user.username
        text = (message.text or "").strip()
        mode = state["mode"]
        if not text or text.startswith("/"):
            prompt_keys = {
                "add_category": "category_add_prompt",
                "delete_category": "category_delete_prompt",
                "rename_category": (
                    "category_rename_id_prompt"
                    if state["step"] == "id"
                    else "category_rename_name_prompt"
                ),
                "edit_product": "product_edit_id_prompt",
                "delete_product": "product_delete_prompt",
                "set_order_status": (
                    "order_id_prompt"
                    if state["step"] == "input"
                    else "order_status_prompt"
                ),
            }
            bot.reply_to(message, translate(user_id, prompt_keys[mode]))
            return

        if mode == "add_category":
            try:
                with database() as connection:
                    connection.execute(
                        "INSERT INTO categories (name) VALUES (?)",
                        (text,),
                    )
            except sqlite3.IntegrityError:
                bot.reply_to(message, translate(user_id, "category_exists"))
                return
            pending_admin.pop(user_id, None)
            log_action(user_id, username, "ADMIN_WIZARD_ADD_CATEGORY", text)
            bot.reply_to(
                message,
                translate(user_id, "category_created", name=text),
            )
            return

        if mode == "delete_category":
            try:
                category_id = int(text)
            except ValueError:
                bot.reply_to(message, translate(user_id, "category_id_invalid"))
                return
            try:
                with database() as connection:
                    result = connection.execute(
                        "DELETE FROM categories WHERE id = ?",
                        (category_id,),
                    )
            except sqlite3.IntegrityError:
                bot.reply_to(message, translate(user_id, "category_has_products"))
                return
            pending_admin.pop(user_id, None)
            key = "category_deleted" if result.rowcount else "category_not_found"
            log_action(user_id, username, "ADMIN_WIZARD_DELETE_CATEGORY", f"id={category_id}, deleted={bool(result.rowcount)}")
            bot.reply_to(message, translate(user_id, key))
            return

        if mode == "rename_category":
            if state["step"] == "id":
                try:
                    state["category_id"] = int(text)
                except ValueError:
                    bot.reply_to(message, translate(user_id, "category_id_invalid"))
                    return
                state["step"] = "name"
                bot.reply_to(
                    message,
                    translate(user_id, "category_rename_name_prompt"),
                )
                return
            try:
                with database() as connection:
                    result = connection.execute(
                        "UPDATE categories SET name = ? WHERE id = ?",
                        (text, state["category_id"]),
                    )
            except sqlite3.IntegrityError:
                bot.reply_to(message, translate(user_id, "category_exists"))
                return
            pending_admin.pop(user_id, None)
            key = "category_renamed" if result.rowcount else "category_not_found"
            log_action(user_id, username, "ADMIN_WIZARD_RENAME_CATEGORY", f"id={state['category_id']}, new_name={text}")
            bot.reply_to(message, translate(user_id, key))
            return

        if mode == "edit_product":
            try:
                product_id = int(text)
            except ValueError:
                bot.reply_to(message, translate(user_id, "product_id_invalid"))
                return
            with database() as connection:
                product = connection.execute(
                    """
                    SELECT p.*, c.name AS category_name
                    FROM products p JOIN categories c ON c.id = p.category_id
                    WHERE p.id = ?
                    """,
                    (product_id,),
                ).fetchone()
            if product is None:
                pending_admin.pop(user_id, None)
                bot.reply_to(message, translate(user_id, "product_not_found"))
                return
            log_action(user_id, username, "ADMIN_WIZARD_EDIT_PRODUCT_SELECTED", f"id={product_id}")
            begin_product_flow(message.chat.id, user_id, product)
            return

        if mode == "delete_product":
            try:
                product_id = int(text)
            except ValueError:
                bot.reply_to(message, translate(user_id, "product_id_invalid"))
                return
            delete_product_from_channel(bot, product_id)
            with database() as connection:
                result = connection.execute(
                    "DELETE FROM products WHERE id = ?",
                    (product_id,),
                )
            pending_admin.pop(user_id, None)
            key = "product_deleted" if result.rowcount else "product_not_found"
            log_action(user_id, username, "ADMIN_WIZARD_DELETE_PRODUCT", f"id={product_id}, deleted={bool(result.rowcount)}")
            bot.reply_to(message, translate(user_id, key))
            return

        if mode == "set_order_status":
            if state["step"] == "input":
                try:
                    state["order_id"] = int(text)
                except ValueError:
                    bot.reply_to(message, translate(user_id, "order_id_invalid"))
                    return
                state["step"] = "status"
                bot.reply_to(message, translate(user_id, "order_status_prompt"))
                return
            allowed = {"new", "processing", "completed", "cancelled"}
            if text.lower() not in allowed:
                bot.reply_to(
                    message,
                    translate(user_id, "order_status_prompt"),
                )
                return
            with database() as connection:
                result = connection.execute(
                    "UPDATE orders SET status = ? WHERE id = ?",
                    (text.lower(), state["order_id"]),
                )
            pending_admin.pop(user_id, None)
            key = "order_status_updated" if result.rowcount else "order_not_found"
            log_action(user_id, username, "ADMIN_WIZARD_SET_ORDER_STATUS", f"id={state['order_id']}, status={text.lower()}")
            bot.reply_to(message, translate(user_id, key))

    @bot.callback_query_handler(
        func=lambda call: (call.data or "").startswith("admin_")
    )
    def handle_admin_callback(call):
        user_id = call.from_user.id
        username = call.from_user.username
        if not is_authenticated_admin(user_id):
            bot.answer_callback_query(call.id, translate(user_id, "admin_required"))
            return

        data = call.data
        try:
            # Category selection in add wizard
            if data.startswith("admin_prod:sel_cat:"):
                cat_target = data.split(":", 2)[2]
                state = pending_admin.get(user_id)
                if not state:
                    bot.answer_callback_query(call.id)
                    return
                if cat_target == "new":
                    state["awaiting_new_category"] = True
                    bot.answer_callback_query(call.id)
                    bot.send_message(
                        call.message.chat.id, translate(user_id, "category_add_prompt")
                    )
                    return
                cat_id = int(cat_target)
                with database() as connection:
                    cat = connection.execute(
                        "SELECT name FROM categories WHERE id = ?", (cat_id,)
                    ).fetchone()
                if cat:
                    state["values"]["category"] = cat["name"]
                state["step"] = "description"
                bot.answer_callback_query(call.id)
                bot.send_message(
                    call.message.chat.id,
                    translate(
                        user_id,
                        "description_prompt",
                        current=state["values"].get("description") or "-",
                    ),
                )
                return

            # Done button in photo uploading step (both Add and Edit)
            if data == "admin_prod:photo_done":
                state = pending_admin.get(user_id)
                bot.answer_callback_query(call.id)
                if not state:
                    return

                if state.get("mode") == "edit_photos":
                    photos = state.get("photos", [])
                    product_id = state["product_id"]
                    if photos:
                        with database() as connection:
                            set_product_photos(connection, product_id, photos)
                        update_channel_post(bot, product_id)
                        log_action(user_id, username, "ADMIN_UPDATE_PHOTOS", f"id={product_id}, count={len(photos)}")
                        bot.send_message(call.message.chat.id, translate(user_id, "field_updated_photos", count=len(photos)))
                    pending_admin.pop(user_id, None)
                    show_product_edit_card(call.message.chat.id, user_id, product_id)
                    return

                if state.get("mode") == "add" and state.get("step") == "photo":
                    show_product_preview(call.message.chat.id, user_id, state)
                return

            # Cancel wizard or editing
            if data in ("admin_prod:cancel", "admin_preview:cancel"):
                state = pending_admin.pop(user_id, None)
                log_action(user_id, username, "ADMIN_WIZARD_CANCELLED")
                bot.answer_callback_query(call.id)
                if state and state.get("mode") in ("edit_single_field", "edit_category_new", "edit_photos"):
                    product_id = state.get("product_id")
                    if product_id:
                        show_product_edit_card(call.message.chat.id, user_id, product_id)
                        return
                bot.send_message(call.message.chat.id, translate(user_id, "cancelled"))
                return

            # Preview: Publish
            if data == "admin_preview:publish":
                state = pending_admin.get(user_id)
                if state and state.get("step") == "preview":
                    log_action(user_id, username, "ADMIN_PREVIEW_PUBLISH")
                    bot.answer_callback_query(call.id)
                    finish_product_save(call.message.chat.id, user_id, state, publish=True)
                else:
                    bot.answer_callback_query(call.id)
                return

            # Preview: Save only in bot
            if data == "admin_preview:save_bot":
                state = pending_admin.get(user_id)
                if state and state.get("step") == "preview":
                    log_action(user_id, username, "ADMIN_PREVIEW_SAVE_BOT")
                    bot.answer_callback_query(call.id)
                    finish_product_save(call.message.chat.id, user_id, state, publish=False)
                else:
                    bot.answer_callback_query(call.id)
                return

            # Preview: Edit again
            if data == "admin_preview:edit":
                state = pending_admin.get(user_id)
                if state:
                    state["step"] = "name"
                    bot.answer_callback_query(call.id)
                    bot.send_message(
                        call.message.chat.id,
                        translate(
                            user_id,
                            "product_name_prompt",
                            current=state["values"].get("name") or "-",
                        ),
                    )
                else:
                    bot.answer_callback_query(call.id)
                return

            # Card-based field editing: admin_edit_field:{prod_id}:{field}
            if data.startswith("admin_edit_field:"):
                parts = data.split(":")
                prod_id = int(parts[1])
                field = parts[2]

                with database() as connection:
                    product = connection.execute(
                        """
                        SELECT p.*, c.name AS category_name
                        FROM products p JOIN categories c ON c.id = p.category_id
                        WHERE p.id = ?
                        """,
                        (prod_id,),
                    ).fetchone()

                if not product:
                    bot.answer_callback_query(call.id, translate(user_id, "product_not_found"))
                    return

                if field == "done":
                    pending_admin.pop(user_id, None)
                    log_action(user_id, username, "ADMIN_EDIT_FINISHED", f"id={prod_id}")
                    bot.answer_callback_query(call.id, translate(user_id, "editing_finished"))
                    bot.send_message(call.message.chat.id, translate(user_id, "editing_finished"))
                    return

                if field == "name":
                    pending_admin[user_id] = {
                        "mode": "edit_single_field",
                        "product_id": prod_id,
                        "field": "name",
                    }
                    bot.answer_callback_query(call.id)
                    bot.send_message(
                        call.message.chat.id,
                        translate(user_id, "edit_prompt_name", current=escape(product["name"])),
                        parse_mode="HTML",
                    )
                    return

                if field == "price":
                    pending_admin[user_id] = {
                        "mode": "edit_single_field",
                        "product_id": prod_id,
                        "field": "price",
                    }
                    bot.answer_callback_query(call.id)
                    bot.send_message(
                        call.message.chat.id,
                        translate(user_id, "edit_prompt_price", current=money(product["price"])),
                        parse_mode="HTML",
                    )
                    return

                if field == "desc":
                    pending_admin[user_id] = {
                        "mode": "edit_single_field",
                        "product_id": prod_id,
                        "field": "desc",
                    }
                    bot.answer_callback_query(call.id)
                    bot.send_message(
                        call.message.chat.id,
                        translate(user_id, "edit_prompt_desc", current=escape(product["description"] or "—")),
                        parse_mode="HTML",
                    )
                    return

                if field == "category":
                    with database() as connection:
                        categories = connection.execute(
                            "SELECT id, name FROM categories ORDER BY name"
                        ).fetchall()
                    bot.answer_callback_query(call.id)
                    bot.send_message(
                        call.message.chat.id,
                        translate(user_id, "edit_select_category"),
                        reply_markup=admin_edit_category_keyboard(user_id, prod_id, categories),
                    )
                    return

                if field == "photos":
                    pending_admin[user_id] = {
                        "mode": "edit_photos",
                        "product_id": prod_id,
                        "photos": [],
                    }
                    bot.answer_callback_query(call.id)
                    bot.send_message(
                        call.message.chat.id,
                        translate(user_id, "edit_prompt_photos"),
                        parse_mode="HTML",
                        reply_markup=admin_photo_upload_keyboard(user_id, 0, allow_skip=False),
                    )
                    return

            # Category selection for product being edited: admin_set_cat:{prod_id}:{action}
            if data.startswith("admin_set_cat:"):
                parts = data.split(":")
                prod_id = int(parts[1])
                action = parts[2]

                if action == "cancel":
                    bot.answer_callback_query(call.id)
                    show_product_edit_card(call.message.chat.id, user_id, prod_id)
                    return

                if action == "new":
                    pending_admin[user_id] = {
                        "mode": "edit_category_new",
                        "product_id": prod_id,
                    }
                    bot.answer_callback_query(call.id)
                    bot.send_message(call.message.chat.id, translate(user_id, "category_add_prompt"))
                    return

                try:
                    cat_id = int(action)
                    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    with database() as connection:
                        cat = connection.execute(
                            "SELECT name FROM categories WHERE id = ?", (cat_id,)
                        ).fetchone()
                        if cat:
                            connection.execute(
                                "UPDATE products SET category_id = ?, updated_at = ? WHERE id = ?",
                                (cat_id, now_str, prod_id),
                            )
                    update_channel_post(bot, prod_id)
                    log_action(user_id, username, "ADMIN_UPDATE_CATEGORY", f"id={prod_id}, cat_id={cat_id}")
                    bot.answer_callback_query(call.id, translate(user_id, "field_updated_category", value=cat["name"] if cat else ""))
                    show_product_edit_card(call.message.chat.id, user_id, prod_id)
                except Exception:
                    logger.exception("Failed to set category for product %s", prod_id)
                    bot.answer_callback_query(call.id, "Ошибка обновления категории")
                return

            # Toggle availability
            if data.startswith("admin_prod:toggle_avail:"):
                prod_id = int(data.split(":")[2])
                with database() as connection:
                    prod = connection.execute(
                        "SELECT is_available, channel_message_ids FROM products WHERE id = ?",
                        (prod_id,),
                    ).fetchone()
                    if not prod:
                        bot.answer_callback_query(
                            call.id, translate(user_id, "product_not_found")
                        )
                        return
                    new_avail = 0 if prod["is_available"] else 1
                    out_stock_at = (
                        datetime.now(timezone.utc).isoformat() if new_avail == 0 else None
                    )
                    connection.execute(
                        "UPDATE products SET is_available = ?, out_of_stock_at = ? WHERE id = ?",
                        (new_avail, out_stock_at, prod_id),
                    )
                update_channel_post(bot, prod_id, is_available=bool(new_avail))
                log_action(user_id, username, "ADMIN_TOGGLE_AVAILABILITY", f"id={prod_id}, new_avail={new_avail}")
                bot.answer_callback_query(
                    call.id,
                    f"Статус: {translate(user_id, 'avail_in_stock' if new_avail else 'avail_out_of_stock')}",
                )
                # Update inline keyboard in message
                has_channel = bool(prod["channel_message_ids"])
                try:
                    bot.edit_message_reply_markup(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        reply_markup=admin_product_actions_keyboard(
                            user_id, prod_id, bool(new_avail), has_channel
                        ),
                    )
                except Exception:
                    pass
                return

            # Edit product -> Open the product edit card!
            if data.startswith("admin_prod:edit:"):
                prod_id = int(data.split(":")[2])
                log_action(user_id, username, "ADMIN_EDIT_PRODUCT_CLICK", f"id={prod_id}")
                bot.answer_callback_query(call.id)
                show_product_edit_card(call.message.chat.id, user_id, prod_id)
                return

            # Publish product to channel
            if data.startswith("admin_prod:publish:"):
                prod_id = int(data.split(":")[2])
                result = publish_product_to_channel(bot, prod_id)
                log_action(user_id, username, "ADMIN_PUBLISH_PRODUCT", f"id={prod_id}, success={bool(result)}")
                if result:
                    bot.answer_callback_query(
                        call.id, translate(user_id, "product_published_channel")
                    )
                    with database() as connection:
                        p = connection.execute(
                            "SELECT is_available FROM products WHERE id = ?", (prod_id,)
                        ).fetchone()
                    try:
                        bot.edit_message_reply_markup(
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id,
                            reply_markup=admin_product_actions_keyboard(
                                user_id, prod_id, bool(p["is_available"]), True
                            ),
                        )
                    except Exception:
                        pass
                else:
                    bot.answer_callback_query(
                        call.id, "Не удалось опубликовать (проверьте CHANNEL_ID и права бота)"
                    )
                return

            # Unpublish product from channel
            if data.startswith("admin_prod:unpublish:"):
                prod_id = int(data.split(":")[2])
                delete_product_from_channel(bot, prod_id)
                log_action(user_id, username, "ADMIN_UNPUBLISH_PRODUCT", f"id={prod_id}")
                bot.answer_callback_query(
                    call.id, translate(user_id, "product_unpublished_channel")
                )
                with database() as connection:
                    p = connection.execute(
                        "SELECT is_available FROM products WHERE id = ?", (prod_id,)
                    ).fetchone()
                try:
                    bot.edit_message_reply_markup(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        reply_markup=admin_product_actions_keyboard(
                            user_id, prod_id, bool(p["is_available"]), False
                        ),
                    )
                except Exception:
                    pass
                return

            # Delete confirmation prompt
            if data.startswith("admin_prod:delete_confirm:"):
                prod_id = int(data.split(":")[2])
                with database() as connection:
                    prod = connection.execute(
                        "SELECT name FROM products WHERE id = ?", (prod_id,)
                    ).fetchone()
                if not prod:
                    bot.answer_callback_query(
                        call.id, translate(user_id, "product_not_found")
                    )
                    return
                bot.answer_callback_query(call.id)
                bot.send_message(
                    call.message.chat.id,
                    translate(
                        user_id,
                        "confirm_delete_product",
                        id=prod_id,
                        name=prod["name"],
                    ),
                    reply_markup=admin_delete_confirm_keyboard(user_id, prod_id),
                )
                return

            # Delete confirmed
            if data.startswith("admin_prod:delete_confirmed:"):
                prod_id = int(data.split(":")[2])
                delete_product_from_channel(bot, prod_id)
                with database() as connection:
                    connection.execute("DELETE FROM products WHERE id = ?", (prod_id,))
                log_action(user_id, username, "ADMIN_DELETE_PRODUCT_CONFIRMED", f"id={prod_id}")
                bot.answer_callback_query(call.id)
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=translate(user_id, "product_deleted"),
                )
                return

            # Delete cancelled
            if data.startswith("admin_prod:delete_cancel:"):
                log_action(user_id, username, "ADMIN_DELETE_CANCELLED")
                bot.answer_callback_query(call.id)
                bot.delete_message(
                    chat_id=call.message.chat.id, message_id=call.message.message_id
                )
                return
        except Exception:
            logger.exception("Error in handle_admin_callback for user %s, data %r", user_id, data)
            bot.answer_callback_query(call.id, "Произошла ошибка при выполнении операции.")
