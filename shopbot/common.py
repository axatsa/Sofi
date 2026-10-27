import hmac
from decimal import Decimal, InvalidOperation

from .config import ADMIN_IDS, ADMIN_PASSWORD, CURRENCY
from .state import authenticated_admin


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def is_authenticated_admin(user_id: int) -> bool:
    return is_admin(user_id) and user_id in authenticated_admin


def verify_admin_password(user_id: int, password: str) -> bool:
    return (
        is_admin(user_id)
        and bool(ADMIN_PASSWORD)
        and hmac.compare_digest(password, ADMIN_PASSWORD)
    )


def money(value: str | Decimal) -> str:
    return f"{Decimal(value):,.2f} {CURRENCY}"


def parse_price(value: str) -> str | None:
    try:
        price = Decimal(value.replace(",", ".").strip())
    except InvalidOperation:
        return None
    if not price.is_finite() or price <= 0:
        return None
    return format(price.quantize(Decimal("0.01")), "f")
