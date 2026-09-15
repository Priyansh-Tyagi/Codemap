from ..services.user_service import find_user, register_user
from ..services.auth_service import authenticate
from ..utils.validators import is_valid_email


def get_user(req):
    authenticate(req)
    return find_user(req.params.get("id"))


def create_user(req):
    if not is_valid_email(req.body.get("email")):
        return None
    return register_user(req.body)
