from telebot import types

from .i18n import translate


CUSTOMER_BUTTONS = {
    "shop": "🛒 Магазин",
    "search": "🔍 Поиск",
    "cart": "🧺 Корзина",
    "my_orders": "📦 Мои заказы",
    "language": "🌐 Язык",
    "admin": "🔐 Админ",
}

ADMIN_BUTTONS = {
    "categories": "📂 Категории",
    "add_category": "➕ Категория",
    "rename_category": "✏️ Переименовать",
    "delete_category": "🗑 Удалить категорию",
    "add_product": "➕ Товар",
    "products": "📋 Товары",
    "edit_product": "✏️ Изменить товар",
    "delete_product": "🗑 Удалить товар",
    "orders": "📑 Заказы",
    "set_order_status": "📝 Статус заказа",
    "admin_logout": "🚪 Выход",
}

# Reverse mapping: emoji label → /command
_BUTTON_TO_COMMAND: dict[str, str] = {}
for cmd, label in {**CUSTOMER_BUTTONS, **ADMIN_BUTTONS}.items():
    _BUTTON_TO_COMMAND[label] = f"/{cmd}"


def button_to_command(text: str) -> str | None:
    """Return the /command for a button label, or None."""
    return _BUTTON_TO_COMMAND.get(text)


def customer_menu_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(
        types.KeyboardButton(CUSTOMER_BUTTONS["shop"]),
        types.KeyboardButton(CUSTOMER_BUTTONS["search"]),
    )
    keyboard.row(
        types.KeyboardButton(CUSTOMER_BUTTONS["cart"]),
        types.KeyboardButton(CUSTOMER_BUTTONS["my_orders"]),
    )
    keyboard.row(
        types.KeyboardButton(CUSTOMER_BUTTONS["language"]),
        types.KeyboardButton(CUSTOMER_BUTTONS["admin"]),
    )
    return keyboard


def admin_menu_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(
        types.KeyboardButton(ADMIN_BUTTONS["categories"]),
        types.KeyboardButton(ADMIN_BUTTONS["add_category"]),
    )
    keyboard.row(
        types.KeyboardButton(ADMIN_BUTTONS["rename_category"]),
        types.KeyboardButton(ADMIN_BUTTONS["delete_category"]),
    )
    keyboard.row(
        types.KeyboardButton(ADMIN_BUTTONS["add_product"]),
        types.KeyboardButton(ADMIN_BUTTONS["products"]),
    )
    keyboard.row(
        types.KeyboardButton(ADMIN_BUTTONS["edit_product"]),
        types.KeyboardButton(ADMIN_BUTTONS["delete_product"]),
    )
    keyboard.row(
        types.KeyboardButton(ADMIN_BUTTONS["orders"]),
        types.KeyboardButton(ADMIN_BUTTONS["set_order_status"]),
    )
    keyboard.row(types.KeyboardButton(ADMIN_BUTTONS["admin_logout"]))
    return keyboard


def language_keyboard(user_id: int):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for language in ("ru", "uz", "en"):
        keyboard.add(
            types.InlineKeyboardButton(
                translate(user_id, f"language_option_{language}"),
                callback_data=f"language:{language}",
            )
        )
    return keyboard


def language_button(user_id: int):
    return types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton(
            translate(user_id, "choose_language"),
            callback_data="language:choose",
        )
    )


def category_keyboard(categories):
    keyboard = types.InlineKeyboardMarkup()
    for category in categories:
        keyboard.add(
            types.InlineKeyboardButton(
                f"{category['name']} ({category['product_count']})",
                callback_data=f"shop:category:{category['id']}",
            )
        )
    return keyboard


def product_keyboard(user_id: int, product_id: int, is_available: bool = True):
    keyboard = types.InlineKeyboardMarkup()
    if is_available:
        keyboard.row(
            types.InlineKeyboardButton(
                translate(user_id, "add_to_cart"),
                callback_data=f"cart:add:{product_id}",
            ),
            types.InlineKeyboardButton(
                translate(user_id, "buy_now"),
                callback_data=f"cart:buynow:{product_id}",
            ),
        )
    return keyboard


def out_of_stock_keyboard(user_id: int, category_id: int | None = None):
    keyboard = types.InlineKeyboardMarkup()
    if category_id:
        keyboard.add(
            types.InlineKeyboardButton(
                translate(user_id, "view_other_products"),
                callback_data=f"shop:category:{category_id}",
            )
        )
    else:
        keyboard.add(
            types.InlineKeyboardButton(
                translate(user_id, "all_categories"),
                callback_data="shop:categories",
            )
        )
    return keyboard


def category_pagination_keyboard(
    user_id: int, category_id: int, page: int, total_pages: int
):
    keyboard = types.InlineKeyboardMarkup()
    nav_buttons = []
    if page > 1:
        nav_buttons.append(
            types.InlineKeyboardButton(
                translate(user_id, "page_prev"),
                callback_data=f"shop:category:{category_id}:{page - 1}",
            )
        )
    nav_buttons.append(
        types.InlineKeyboardButton(
            f"{page}/{total_pages}",
            callback_data="noop",
        )
    )
    if page < total_pages:
        nav_buttons.append(
            types.InlineKeyboardButton(
                translate(user_id, "page_next"),
                callback_data=f"shop:category:{category_id}:{page + 1}",
            )
        )
    keyboard.row(*nav_buttons)
    keyboard.add(
        types.InlineKeyboardButton(
            translate(user_id, "all_categories"),
            callback_data="shop:categories",
        )
    )
    return keyboard


def admin_photo_upload_keyboard(user_id: int, count: int):
    keyboard = types.InlineKeyboardMarkup()
    if count > 0:
        keyboard.add(
            types.InlineKeyboardButton(
                f"{translate(user_id, 'btn_done')} ({count}/5)",
                callback_data="admin_prod:photo_done",
            )
        )
    keyboard.add(
        types.InlineKeyboardButton(
            translate(user_id, "btn_cancel"),
            callback_data="admin_prod:cancel",
        )
    )
    return keyboard


def admin_select_category_keyboard(user_id: int, categories):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton(
            cat["name"],
            callback_data=f"admin_prod:sel_cat:{cat['id']}",
        )
        for cat in categories
    ]
    keyboard.add(*buttons)
    keyboard.add(
        types.InlineKeyboardButton(
            translate(user_id, "category_new_button"),
            callback_data="admin_prod:sel_cat:new",
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            translate(user_id, "btn_cancel"),
            callback_data="admin_prod:cancel",
        )
    )
    return keyboard


def admin_product_preview_keyboard(user_id: int):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(
        types.InlineKeyboardButton(
            translate(user_id, "btn_publish_channel"),
            callback_data="admin_preview:publish",
        )
    )
    keyboard.row(
        types.InlineKeyboardButton(
            translate(user_id, "btn_save_bot"),
            callback_data="admin_preview:save_bot",
        )
    )
    keyboard.row(
        types.InlineKeyboardButton(
            translate(user_id, "btn_edit"),
            callback_data="admin_preview:edit",
        ),
        types.InlineKeyboardButton(
            translate(user_id, "btn_cancel"),
            callback_data="admin_preview:cancel",
        ),
    )
    return keyboard


def admin_product_actions_keyboard(
    user_id: int, product_id: int, is_available: bool, has_channel_post: bool
):
    keyboard = types.InlineKeyboardMarkup()
    status_text = (
        translate(user_id, "avail_in_stock")
        if is_available
        else translate(user_id, "avail_out_of_stock")
    )
    keyboard.row(
        types.InlineKeyboardButton(
            translate(user_id, "status_available_toggle", status=status_text),
            callback_data=f"admin_prod:toggle_avail:{product_id}",
        )
    )
    keyboard.row(
        types.InlineKeyboardButton(
            translate(user_id, "btn_edit"),
            callback_data=f"admin_prod:edit:{product_id}",
        )
    )
    if has_channel_post:
        keyboard.row(
            types.InlineKeyboardButton(
                translate(user_id, "btn_unpublish_channel"),
                callback_data=f"admin_prod:unpublish:{product_id}",
            )
        )
    else:
        keyboard.row(
            types.InlineKeyboardButton(
                translate(user_id, "btn_publish_channel"),
                callback_data=f"admin_prod:publish:{product_id}",
            )
        )
    keyboard.row(
        types.InlineKeyboardButton(
            translate(user_id, "btn_delete_full"),
            callback_data=f"admin_prod:delete_confirm:{product_id}",
        )
    )
    return keyboard


def admin_delete_confirm_keyboard(user_id: int, product_id: int):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(
        types.InlineKeyboardButton(
            translate(user_id, "btn_confirm_delete"),
            callback_data=f"admin_prod:delete_confirmed:{product_id}",
        ),
        types.InlineKeyboardButton(
            translate(user_id, "btn_cancel"),
            callback_data=f"admin_prod:delete_cancel:{product_id}",
        ),
    )
    return keyboard


def cart_keyboard(user_id: int, items):
    keyboard = types.InlineKeyboardMarkup()
    for item in items:
        keyboard.add(
            types.InlineKeyboardButton(
                translate(user_id, "remove_from_cart", name=item["name"]),
                callback_data=f"cart:remove:{item['id']}",
            )
        )
    keyboard.add(
        types.InlineKeyboardButton(
            translate(user_id, "checkout"),
            callback_data="checkout",
        )
    )
    return keyboard
