from .user_service import find_user


def issue_token(user):
    return f"token-for-{user.id or 'new'}"


def verify_token(token):
    user_id = token.replace("token-for-", "")
    return find_user(user_id)


def authenticate(req):
    token = req.headers.get("authorization") if req.headers else None
    return verify_token(token) if token else None
