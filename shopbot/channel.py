import json
import logging
from decimal import Decimal
from html import escape
from telebot import types
from telebot.apihelper import ApiTelegramException

from .common import money
from .config import CHANNEL_ID
from .db import database, get_product_photos

logger = logging.getLogger("tg_shop.channel")

_cached_bot_username: str | None = None


def get_bot_username(bot) -> str:
    global _cached_bot_username
    if _cached_bot_username:
        return _cached_bot_username
    me = bot.get_me()
    _cached_bot_username = me.username or ""
    return _cached_bot_username


def format_product_code(product_id: int) -> str:
    return f"#P{product_id:04d}"


def format_channel_caption(
    name: str,
    product_id: int,
    description: str,
    price: str | Decimal,
    is_available: bool = True,
) -> str:
    code = format_product_code(product_id)
    price_str = money(price)
    desc_str = f"\n\n{escape(description)}" if description else ""
    if not is_available:
        return (
            f"❌ <b>НЕТ В НАЛИЧИИ</b>\n"
            f"<b>{escape(name)}</b>\n"
            f"Артикул / ID: {code}"
            f"{desc_str}\n"
            f"💰 Цена: <b>{price_str}</b>"
        )
    return (
        f"<b>{escape(name)}</b>\n"
        f"Артикул / ID: {code}"
        f"{desc_str}\n"
        f"💰 Цена: <b>{price_str}</b>"
    )


def order_button_markup(bot_username: str, product_id: int) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    url = f"https://t.me/{bot_username}?start=order_{product_id}"
    markup.add(types.InlineKeyboardButton("🛒 Заказать", url=url))
    return markup


def publish_product_to_channel(bot, product_id: int) -> list[int] | None:
    if not CHANNEL_ID:
        logger.warning("CHANNEL_ID is not configured, skipping channel publish.")
        return None

    with database() as connection:
        product = connection.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        if not product:
            return None
        photos = get_product_photos(connection, product_id)

    bot_username = get_bot_username(bot)
    is_avail = bool(product["is_available"])
    caption = format_channel_caption(
        name=product["name"],
        product_id=product["id"],
        description=product["description"],
        price=product["price"],
        is_available=is_avail,
    )
    markup = order_button_markup(bot_username, product["id"]) if is_avail else None

    msg_ids: list[int] = []

    try:
        if len(photos) == 1:
            msg = bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=photos[0],
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup,
            )
            msg_ids = [msg.message_id]
        elif len(photos) > 1:
            media = [
                types.InputMediaPhoto(photos[0], caption=caption, parse_mode="HTML")
            ]
            for photo_id in photos[1:5]:
                media.append(types.InputMediaPhoto(photo_id))
            album_msgs = bot.send_media_group(chat_id=CHANNEL_ID, media=media)
            msg_ids = [m.message_id for m in album_msgs]
            if is_avail and markup:
                service_msg = bot.send_message(
                    chat_id=CHANNEL_ID,
                    text="Для заказа товара нажмите кнопку ниже ⬇️",
                    reply_markup=markup,
                )
                msg_ids.append(service_msg.message_id)
        else:
            msg = bot.send_message(
                chat_id=CHANNEL_ID,
                text=caption,
                parse_mode="HTML",
                reply_markup=markup,
            )
            msg_ids = [msg.message_id]

        with database() as connection:
            connection.execute(
                "UPDATE products SET channel_message_ids = ? WHERE id = ?",
                (json.dumps(msg_ids), product_id),
            )
        return msg_ids
    except ApiTelegramException as e:
        logger.error("Failed to publish product %s to channel: %s", product_id, e)
        return None


def update_channel_post(bot, product_id: int, is_available: bool | None = None) -> bool:
    if not CHANNEL_ID:
        return False

    with database() as connection:
        product = connection.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        if not product:
            return False
        photos = get_product_photos(connection, product_id)

    if is_available is None:
        is_available = bool(product["is_available"])

    raw_ids = product["channel_message_ids"]
    if not raw_ids:
        # If product was never published or was deleted from channel (>7 days ago),
        # re-publish if it's now available again.
        if is_available:
            return publish_product_to_channel(bot, product_id) is not None
        return False

    try:
        msg_ids: list[int] = json.loads(raw_ids)
    except Exception:
        msg_ids = []

    if not msg_ids:
        if is_available:
            return publish_product_to_channel(bot, product_id) is not None
        return False

    bot_username = get_bot_username(bot)
    caption = format_channel_caption(
        name=product["name"],
        product_id=product["id"],
        description=product["description"],
        price=product["price"],
        is_available=is_available,
    )
    markup = order_button_markup(bot_username, product["id"]) if is_available else None

    try:
        # 1. Update caption or text of primary message
        if photos:
            # Single or multi-photo: first message has the caption
            bot.edit_message_caption(
                chat_id=CHANNEL_ID,
                message_id=msg_ids[0],
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup if (len(photos) == 1 and is_available) else None,
            )
        else:
            bot.edit_message_text(
                chat_id=CHANNEL_ID,
                message_id=msg_ids[0],
                text=caption,
                parse_mode="HTML",
                reply_markup=markup if is_available else None,
            )

        # 2. Update service message for multi-photo post
        if len(photos) > 1:
            has_service_msg = len(msg_ids) > len(photos)
            if is_available:
                if has_service_msg:
                    try:
                        bot.edit_message_text(
                            chat_id=CHANNEL_ID,
                            message_id=msg_ids[-1],
                            text="Для заказа товара нажмите кнопку ниже ⬇️",
                            reply_markup=markup,
                        )
                    except ApiTelegramException:
                        service_msg = bot.send_message(
                            chat_id=CHANNEL_ID,
                            text="Для заказа товара нажмите кнопку ниже ⬇️",
                            reply_markup=markup,
                        )
                        msg_ids[-1] = service_msg.message_id
                        with database() as connection:
                            connection.execute(
                                "UPDATE products SET channel_message_ids = ? WHERE id = ?",
                                (json.dumps(msg_ids), product_id),
                            )
                else:
                    service_msg = bot.send_message(
                        chat_id=CHANNEL_ID,
                        text="Для заказа товара нажмите кнопку ниже ⬇️",
                        reply_markup=markup,
                    )
                    msg_ids.append(service_msg.message_id)
                    with database() as connection:
                        connection.execute(
                            "UPDATE products SET channel_message_ids = ? WHERE id = ?",
                            (json.dumps(msg_ids), product_id),
                        )
            else:
                # Remove order button from service message
                if has_service_msg:
                    try:
                        bot.edit_message_text(
                            chat_id=CHANNEL_ID,
                            message_id=msg_ids[-1],
                            text="❌ Товар временно распродан",
                            reply_markup=None,
                        )
                    except ApiTelegramException:
                        pass
        return True
    except ApiTelegramException as e:
        logger.warning(
            "Could not edit message in channel for product %s (%s). Attempting republish if in stock.",
            product_id,
            e,
        )
        # Message was likely deleted manually or expired
        with database() as connection:
            connection.execute(
                "UPDATE products SET channel_message_ids = NULL WHERE id = ?",
                (product_id,),
            )
        if is_available:
            return publish_product_to_channel(bot, product_id) is not None
        return False


def delete_product_from_channel(bot, product_id: int) -> bool:
    if not CHANNEL_ID:
        return False

    with database() as connection:
        product = connection.execute(
            "SELECT channel_message_ids FROM products WHERE id = ?", (product_id,)
        ).fetchone()

    if not product or not product["channel_message_ids"]:
        return False

    try:
        msg_ids = json.loads(product["channel_message_ids"])
    except Exception:
        msg_ids = []

    for msg_id in msg_ids:
        try:
            bot.delete_message(chat_id=CHANNEL_ID, message_id=msg_id)
        except ApiTelegramException as e:
            logger.debug("Could not delete message %s from channel: %s", msg_id, e)

    with database() as connection:
        connection.execute(
            "UPDATE products SET channel_message_ids = NULL WHERE id = ?",
            (product_id,),
        )
    return True
