from ..services.order_service import find_order, place_order
from ..utils.validators import is_non_empty_string
from ..utils.formatting import format_date


def get_order(req):
    order = find_order(req.params.get("id"))
    return {**order, "placed_on": format_date()}


def create_order(req):
    if not is_non_empty_string(req.body.get("item")):
        return None
    return place_order(req.body)
