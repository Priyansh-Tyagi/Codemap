from .routes.user_routes import register_user_routes
from .routes.order_routes import register_order_routes


def start_app(router):
    register_user_routes(router)
    register_order_routes(router)
