from ..models.user import User
from .auth_service import issue_token
from ..utils.validators import is_valid_email


def find_user(user_id):
    return User(user_id, "placeholder@example.com")


def register_user(data):
    if not is_valid_email(data.get("email")):
        return None
    user = User(None, data.get("email"))
    token = issue_token(user)
    return {"user": user, "token": token}
