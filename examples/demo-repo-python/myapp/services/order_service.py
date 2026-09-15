from ..models.order import Order
from .user_service import find_user
from ..utils.validators import is_non_empty_string


def find_order(order_id):
    return Order(order_id, None, None)


def place_order(data):
    if not is_non_empty_string(data.get("item")):
        return None
    user = find_user(data.get("user_id"))
    return Order(None, user, data.get("item"))
