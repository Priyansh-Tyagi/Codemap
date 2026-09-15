from ..controllers.order_controller import get_order, create_order
from ..utils.validators import is_non_empty_string


def register_order_routes(router):
    router.get("/orders/<id>", get_order)
    router.post("/orders", lambda req: create_order(req) if is_non_empty_string(req.body.get("item")) else None)
