from ..controllers.user_controller import get_user, create_user
from ..utils.validators import is_valid_email


def register_user_routes(router):
    router.get("/users/<id>", get_user)
    router.post("/users", lambda req: create_user(req) if is_valid_email(req.body.get("email")) else None)
