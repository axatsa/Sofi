import re
import sqlite3
from decimal import Decimal
from html import escape

import telebot

from .admin import register_admin_handlers
from .common import is_admin, money, verify_admin_password
from .config import ADMIN_IDS, ADMIN_PASSWORD, TOKEN, logger
from .db import database, get_product_photos, initialize_database
from .i18n import set_language, translate
from .keyboards import (
    admin_menu_keyboard,
    button_to_command,
    cart_keyboard,
    category_keyboard,
    customer_menu_keyboard,
    language_keyboard,
    out_of_stock_keyboard,
    product_keyboard,
)
from .state import (
    authenticated_admin,
    pending_admin,
    pending_admin_login,
    pending_checkout,
    pending_search,
)

bot = telebot.TeleBot(TOKEN)


@bot.message_handler(
    content_types=["text"],
    func=lambda message: message.from_user.id in pending_admin_login,
)
def handle_admin_password(message):
    user_id = message.from_user.id
    pending_admin_login.discard(user_id)
    if not message.text or message.text.startswith("/"):
        bot.reply_to(message, translate(user_id, "admin_login_cancelled"))
        return
    if not verify_admin_password(user_id, message.text):
        bot.reply_to(message, translate(user_id, "admin_password_invalid"))
        return
    authenticated_admin.add(user_id)
    bot.reply_to(
        message,
        translate(user_id, "admin_logged_in"),
        reply_markup=admin_menu_keyboard(),
    )


def send_product(chat_id: int, user_id: int, product, reply_markup=None):
    if reply_markup is None:
        reply_markup = product_keyboard(
            user_id, product["id"], is_available=bool(product["is_available"])
        )

    code = f"#P{product['id']:04d}"
    text = (
        f"<b>{escape(product['name'])}</b>\n"
        f"Артикул / ID: {code}\n\n"
        f"{escape(product['description'] or translate(user_id, 'no_description'))}\n"
        f"{translate(user_id, 'price', price=money(product['price']))}"
    )

    with database() as connection:
        photos = get_product_photos(connection, product["id"])

    if len(photos) == 1:
        bot.send_photo(
            chat_id,
            photos[0],
            caption=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    elif len(photos) > 1:
        media = [
            telebot.types.InputMediaPhoto(photos[0], caption=text, parse_mode="HTML")
        ]
        for photo_id in photos[1:5]:
            media.append(telebot.types.InputMediaPhoto(photo_id))
        bot.send_media_group(chat_id, media)
        bot.send_message(
            chat_id,
            "Для заказа выберите действие:",
            reply_markup=reply_markup,
        )
    else:
        bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=reply_markup)


def show_categories(chat_id: int, user_id: int):
    with database() as connection:
        categories = connection.execute(
            """
            SELECT c.id, c.name, COUNT(p.id) AS product_count
            FROM categories c
            LEFT JOIN products p ON p.category_id = c.id AND p.is_available = 1
            GROUP BY c.id
            ORDER BY c.name
            """
        ).fetchall()
    if not categories:
        bot.send_message(chat_id, translate(user_id, "shop_empty"))
        return
    bot.send_message(
        chat_id,
        translate(user_id, "choose_category"),
        reply_markup=category_keyboard(categories),
    )


def show_category_page(chat_id: int, user_id: int, category_id: int, page: int = 1):
    with database() as connection:
        products = connection.execute(
            """
            SELECT * FROM products
            WHERE category_id = ? AND is_available = 1
            ORDER BY id
            """,
            (category_id,),
        ).fetchall()
        category = connection.execute(
            "SELECT name FROM categories WHERE id = ?", (category_id,)
        ).fetchone()

    if not products:
        bot.send_message(
            chat_id,
            translate(user_id, "no_products_in_category"),
            reply_markup=out_of_stock_keyboard(user_id, None),
        )
        return

    total = len(products)
    page = max(1, min(page, total))
    product = products[page - 1]

    # Build pagination keyboard
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.row(
        telebot.types.InlineKeyboardButton(
            translate(user_id, "add_to_cart"),
            callback_data=f"cart:add:{product['id']}",
        ),
        telebot.types.InlineKeyboardButton(
            translate(user_id, "buy_now"),
            callback_data=f"cart:buynow:{product['id']}",
        ),
    )

    nav_row = []
    if page > 1:
        nav_row.append(
            telebot.types.InlineKeyboardButton(
                translate(user_id, "page_prev"),
                callback_data=f"shop:cat:{category_id}:{page - 1}",
            )
        )
    nav_row.append(
        telebot.types.InlineKeyboardButton(
            f"{page}/{total}",
            callback_data="noop",
        )
    )
    if page < total:
        nav_row.append(
            telebot.types.InlineKeyboardButton(
                translate(user_id, "page_next"),
                callback_data=f"shop:cat:{category_id}:{page + 1}",
            )
        )
    keyboard.row(*nav_row)
    keyboard.add(
        telebot.types.InlineKeyboardButton(
            translate(user_id, "all_categories"),
            callback_data="shop:categories",
        )
    )

    send_product(chat_id, user_id, product, reply_markup=keyboard)


def show_cart(chat_id: int, user_id: int):
    with database() as connection:
        items = connection.execute(
            """
            SELECT p.id, p.name, p.price, ci.quantity
            FROM cart_items ci
            JOIN products p ON p.id = ci.product_id
            WHERE ci.user_id = ?
            ORDER BY p.name
            """,
            (user_id,),
        ).fetchall()
    if not items:
        bot.send_message(chat_id, translate(user_id, "cart_empty"))
        return
    total = sum(
        (Decimal(item["price"]) * item["quantity"] for item in items),
        Decimal(0),
    )
    lines = [translate(user_id, "your_cart")]
    lines.extend(
        translate(
            user_id,
            "cart_item",
            name=escape(item["name"]),
            quantity=item["quantity"],
            price=money(Decimal(item["price"]) * item["quantity"]),
        )
        for item in items
    )
    lines.append(translate(user_id, "cart_total", total=money(total)))
    bot.send_message(
        chat_id,
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=cart_keyboard(user_id, items),
    )


def handle_order_deeplink(message, param: str):
    user_id = message.from_user.id
    match = re.search(r"\d+", param)
    if not match:
        bot.reply_to(message, translate(user_id, "product_not_found"))
        return
    product_id = int(match.group(0))

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
        bot.reply_to(message, translate(user_id, "product_not_found"))
        return

    if not product["is_available"]:
        bot.reply_to(
            message,
            translate(user_id, "out_of_stock_message"),
            reply_markup=out_of_stock_keyboard(user_id, product["category_id"]),
        )
        return

    send_product(message.chat.id, user_id, product)


@bot.message_handler(commands=["start", "help"])
def start(message):
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip().startswith("order_"):
        handle_order_deeplink(message, parts[1].strip())
        return

    text = translate(user_id, "start_customer")
    bot.reply_to(
        message,
        text,
        parse_mode="HTML",
        reply_markup=customer_menu_keyboard(),
    )


@bot.message_handler(commands=["language", "lang"])
def choose_language(message):
    user_id = message.from_user.id
    bot.reply_to(
        message,
        translate(user_id, "language_prompt"),
        reply_markup=language_keyboard(user_id),
    )


@bot.message_handler(commands=["admin"])
def admin_help(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(
            message,
            translate(user_id, "admin_required"),
        )
        return
    if not ADMIN_PASSWORD:
        bot.reply_to(message, translate(user_id, "admin_password_unconfigured"))
        return
    authenticated_admin.discard(user_id)
    pending_admin.pop(user_id, None)
    pending_checkout.pop(user_id, None)
    pending_search.discard(user_id)
    pending_admin_login.add(user_id)
    bot.reply_to(
        message,
        translate(user_id, "admin_password_prompt"),
        reply_markup=customer_menu_keyboard(),
    )


@bot.message_handler(commands=["admin_logout"])
def admin_logout(message):
    user_id = message.from_user.id
    authenticated_admin.discard(user_id)
    pending_admin_login.discard(user_id)
    pending_admin.pop(user_id, None)
    bot.reply_to(
        message,
        translate(user_id, "admin_logged_out"),
        reply_markup=customer_menu_keyboard(),
    )


@bot.message_handler(commands=["shop"])
def shop_command(message):
    show_categories(message.chat.id, message.from_user.id)


@bot.message_handler(commands=["search"])
def search_command(message):
    user_id = message.from_user.id
    query = message.text.partition(" ")[2].strip()
    if not query:
        pending_search.add(user_id)
        bot.reply_to(message, translate(user_id, "search_prompt"))
        return
    pending_search.discard(user_id)
    with database() as connection:
        products = connection.execute(
            """
            SELECT * FROM products
            WHERE (name LIKE ? COLLATE NOCASE OR description LIKE ? COLLATE NOCASE)
              AND is_available = 1
            ORDER BY name LIMIT 20
            """,
            (f"%{query}%", f"%{query}%"),
        ).fetchall()
    if not products:
        bot.reply_to(message, translate(user_id, "no_products_found"))
        return
    for product in products:
        send_product(message.chat.id, user_id, product)


@bot.message_handler(commands=["cart"])
def cart_command(message):
    show_cart(message.chat.id, message.from_user.id)


@bot.message_handler(commands=["my_orders"])
def my_orders_command(message):
    user_id = message.from_user.id
    with database() as connection:
        orders = connection.execute(
            """
            SELECT id, status, total, created_at FROM orders
            WHERE user_id = ? ORDER BY id DESC LIMIT 10
            """,
            (user_id,),
        ).fetchall()
    if not orders:
        bot.reply_to(message, translate(user_id, "no_orders_yet"))
        return
    bot.reply_to(
        message,
        "\n".join(
            translate(
                user_id,
                "my_order",
                id=order["id"],
                status=translate(user_id, f"status_{order['status']}"),
                total=money(order["total"]),
                created_at=order["created_at"],
            )
            for order in orders
        ),
    )


@bot.message_handler(commands=["cancel"])
def cancel_command(message):
    user_id = message.from_user.id
    pending_admin.pop(user_id, None)
    pending_admin_login.discard(user_id)
    pending_checkout.pop(user_id, None)
    pending_search.discard(user_id)
    bot.reply_to(message, translate(user_id, "cancelled"))


@bot.callback_query_handler(func=lambda _: True)
def callback_handler(call):
    user_id = call.from_user.id
    try:
        if call.data == "noop":
            bot.answer_callback_query(call.id)
            return

        if call.data == "language:choose":
            bot.answer_callback_query(call.id)
            bot.send_message(
                call.message.chat.id,
                translate(user_id, "language_prompt"),
                reply_markup=language_keyboard(user_id),
            )
            return

        if call.data.startswith("language:"):
            language = call.data.partition(":")[2]
            set_language(user_id, language)
            bot.answer_callback_query(call.id)
            bot.send_message(
                call.message.chat.id,
                translate(user_id, "language_saved"),
            )
            return

        if call.data == "shop:categories":
            bot.answer_callback_query(call.id)
            show_categories(call.message.chat.id, user_id)
            return

        # Category page with pagination: shop:cat:{category_id}:{page}
        if call.data.startswith("shop:cat:"):
            parts = call.data.split(":")
            category_id = int(parts[2])
            page = int(parts[3]) if len(parts) > 3 else 1
            bot.answer_callback_query(call.id)
            show_category_page(call.message.chat.id, user_id, category_id, page)
            return

        parts = call.data.split(":")
        if len(parts) == 3 and parts[:2] == ["shop", "category"]:
            category_id = int(parts[2])
            bot.answer_callback_query(call.id)
            show_category_page(call.message.chat.id, user_id, category_id, 1)
            return

        if len(parts) == 3 and parts[:2] == ["cart", "add"]:
            product_id = int(parts[2])
            with database() as connection:
                product = connection.execute(
                    "SELECT id, is_available FROM products WHERE id = ?", (product_id,)
                ).fetchone()
                if product is None or not product["is_available"]:
                    bot.answer_callback_query(
                        call.id,
                        translate(user_id, "product_unavailable"),
                    )
                    return
                connection.execute(
                    """
                    INSERT INTO cart_items (user_id, product_id, quantity)
                    VALUES (?, ?, 1)
                    ON CONFLICT(user_id, product_id)
                    DO UPDATE SET quantity = quantity + 1
                    """,
                    (user_id, product_id),
                )
            bot.answer_callback_query(call.id, translate(user_id, "added_to_cart"))
            return

        # Buy now button: adds to cart and initiates immediate checkout
        if len(parts) == 3 and parts[:2] == ["cart", "buynow"]:
            product_id = int(parts[2])
            with database() as connection:
                product = connection.execute(
                    "SELECT id, is_available FROM products WHERE id = ?", (product_id,)
                ).fetchone()
                if product is None or not product["is_available"]:
                    bot.answer_callback_query(
                        call.id,
                        translate(user_id, "product_unavailable"),
                    )
                    return
                connection.execute(
                    """
                    INSERT INTO cart_items (user_id, product_id, quantity)
                    VALUES (?, ?, 1)
                    ON CONFLICT(user_id, product_id)
                    DO UPDATE SET quantity = quantity + 1
                    """,
                    (user_id, product_id),
                )
            pending_checkout[user_id] = {"step": "name"}
            bot.answer_callback_query(call.id)
            bot.send_message(
                call.message.chat.id,
                translate(user_id, "checkout_name_prompt"),
            )
            return

        if len(parts) == 3 and parts[:2] == ["cart", "remove"]:
            product_id = int(parts[2])
            with database() as connection:
                connection.execute(
                    "DELETE FROM cart_items WHERE user_id = ? AND product_id = ?",
                    (user_id, product_id),
                )
            bot.answer_callback_query(call.id, translate(user_id, "removed_from_cart"))
            show_cart(call.message.chat.id, user_id)
            return

        if call.data == "checkout":
            with database() as connection:
                has_items = connection.execute(
                    "SELECT 1 FROM cart_items WHERE user_id = ? LIMIT 1",
                    (user_id,),
                ).fetchone()
            if not has_items:
                bot.answer_callback_query(
                    call.id,
                    translate(user_id, "checkout_cart_empty"),
                )
                return
            pending_checkout[user_id] = {"step": "name"}
            bot.answer_callback_query(call.id)
            bot.send_message(
                call.message.chat.id,
                translate(user_id, "checkout_name_prompt"),
            )
    except (IndexError, ValueError, sqlite3.Error):
        logger.exception("Could not process callback %r", call.data)
        bot.answer_callback_query(call.id, translate(user_id, "callback_error"))


@bot.message_handler(
    content_types=["text"],
    func=lambda message: message.from_user.id in pending_checkout
    and message.from_user.id not in pending_admin
    and message.from_user.id not in pending_admin_login,
)
def handle_checkout_input(message):
    user_id = message.from_user.id
    state = pending_checkout[user_id]
    if not message.text or message.text.startswith("/"):
        bot.reply_to(message, translate(user_id, "checkout_text_only"))
        return
    field_prompts = {
        "name": ("name", "phone_prompt"),
        "phone": ("phone", "address_prompt"),
        "address": ("address", None),
    }
    field, next_prompt_key = field_prompts[state["step"]]
    state[field] = message.text.strip()
    if next_prompt_key:
        state["step"] = {"name": "phone", "phone": "address"}[state["step"]]
        bot.reply_to(message, translate(user_id, next_prompt_key))
        return
    create_order(message, state)


@bot.message_handler(
    content_types=["text"],
    func=lambda message: message.from_user.id in pending_search,
)
def handle_search_input(message):
    user_id = message.from_user.id
    if not message.text or message.text.startswith("/"):
        bot.reply_to(message, translate(user_id, "search_prompt"))
        return
    pending_search.discard(user_id)
    with database() as connection:
        products = connection.execute(
            """
            SELECT * FROM products
            WHERE (name LIKE ? COLLATE NOCASE OR description LIKE ? COLLATE NOCASE)
              AND is_available = 1
            ORDER BY name LIMIT 20
            """,
            (f"%{message.text.strip()}%", f"%{message.text.strip()}%"),
        ).fetchall()
    if not products:
        bot.reply_to(message, translate(user_id, "no_products_found"))
        return
    for product in products:
        send_product(message.chat.id, user_id, product)


def create_order(message, customer):
    user_id = message.from_user.id
    with database() as connection:
        items = connection.execute(
            """
            SELECT p.id, p.name, p.price, ci.quantity
            FROM cart_items ci JOIN products p ON p.id = ci.product_id
            WHERE ci.user_id = ?
            """,
            (user_id,),
        ).fetchall()
        if not items:
            pending_checkout.pop(user_id, None)
            bot.reply_to(message, translate(user_id, "cart_empty"))
            return
        total = sum(
            (Decimal(item["price"]) * item["quantity"] for item in items),
            Decimal(0),
        )
        cursor = connection.execute(
            """
            INSERT INTO orders (user_id, customer_name, phone, address, total)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user_id,
                customer["name"],
                customer["phone"],
                customer["address"],
                format(total, "f"),
            ),
        )
        order_id = cursor.lastrowid
        connection.executemany(
            """
            INSERT INTO order_items (order_id, product_name, unit_price, quantity)
            VALUES (?, ?, ?, ?)
            """,
            [
                (order_id, item["name"], item["price"], item["quantity"])
                for item in items
            ],
        )
        connection.execute("DELETE FROM cart_items WHERE user_id = ?", (user_id,))
    pending_checkout.pop(user_id, None)
    bot.reply_to(
        message,
        translate(
            user_id,
            "order_placed",
            id=order_id,
            total=money(total),
        ),
    )
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(
                admin_id,
                translate(
                    admin_id,
                    "new_order_notification",
                    id=order_id,
                    name=customer["name"],
                    phone=customer["phone"],
                    address=customer["address"],
                    total=money(total),
                ),
            )
        except telebot.apihelper.ApiTelegramException:
            logger.exception(
                "Could not notify admin %s about order %s",
                admin_id,
                order_id,
            )


@bot.message_handler(
    content_types=["text"],
    func=lambda message: (
        message.from_user.id not in pending_checkout
        and message.from_user.id not in pending_search
        and message.from_user.id not in pending_admin
        and message.from_user.id not in pending_admin_login
    ),
)
def handle_customer_text(message):
    user_id = message.from_user.id
    raw_text = (message.text or "").strip()

    # 1. Emoji buttons navigation
    command = button_to_command(raw_text)
    if command:
        message.text = command
        bot.process_new_messages([message])
        return

    # 2. Product ID direct search (e.g., 42, #42, #P0042, P0042, P42)
    id_match = re.match(r"^#?[pP]?0*(\d+)$", raw_text)
    if id_match:
        product_id = int(id_match.group(1))
        with database() as connection:
            product = connection.execute(
                """
                SELECT p.*, c.name AS category_name
                FROM products p JOIN categories c ON c.id = p.category_id
                WHERE p.id = ?
                """,
                (product_id,),
            ).fetchone()
        if product:
            if not product["is_available"]:
                bot.reply_to(
                    message,
                    translate(user_id, "out_of_stock_message"),
                    reply_markup=out_of_stock_keyboard(
                        user_id, product["category_id"]
                    ),
                )
            else:
                send_product(message.chat.id, user_id, product)
            return

    # 3. Default fallback: text search
    if not raw_text.startswith("/"):
        with database() as connection:
            products = connection.execute(
                """
                SELECT * FROM products
                WHERE (name LIKE ? COLLATE NOCASE OR description LIKE ? COLLATE NOCASE)
                  AND is_available = 1
                ORDER BY name LIMIT 5
                """,
                (f"%{raw_text}%", f"%{raw_text}%"),
            ).fetchall()
        if products:
            for prod in products:
                send_product(message.chat.id, user_id, prod)
            return


def main():
    initialize_database()
    register_admin_handlers(bot, pending_admin)
    logger.info("Starting Telegram shop bot")
    bot.infinity_polling(skip_pending=True)


if __name__ == "__main__":
    main()
