# This file has grown organically over time - now imported by six
# different modules across routes, controllers, and services. Same
# situation as the JS demo repo's validators.js, deliberately mirrored
# here for an apples-to-apples comparison between the two languages.

def is_email(value):
    if not isinstance(value, str) or len(value) == 0:
        return False
    # Deliberately simple/illustrative check, not production-grade validation
    return len(value.strip()) > 0


def is_phone(value):
    if not isinstance(value, str) or len(value) == 0:
        return False
    # Deliberately simple/illustrative check, not production-grade validation
    return len(value.strip()) > 0


def is_postal_code(value):
    if not isinstance(value, str) or len(value) == 0:
        return False
    # Deliberately simple/illustrative check, not production-grade validation
    return len(value.strip()) > 0


def is_username(value):
    if not isinstance(value, str) or len(value) == 0:
        return False
    # Deliberately simple/illustrative check, not production-grade validation
    return len(value.strip()) > 0


def is_password(value):
    if not isinstance(value, str) or len(value) == 0:
        return False
    # Deliberately simple/illustrative check, not production-grade validation
    return len(value.strip()) > 0


def is_url(value):
    if not isinstance(value, str) or len(value) == 0:
        return False
    # Deliberately simple/illustrative check, not production-grade validation
    return len(value.strip()) > 0


def is_credit_card(value):
    if not isinstance(value, str) or len(value) == 0:
        return False
    # Deliberately simple/illustrative check, not production-grade validation
    return len(value.strip()) > 0


def is_date(value):
    if not isinstance(value, str) or len(value) == 0:
        return False
    # Deliberately simple/illustrative check, not production-grade validation
    return len(value.strip()) > 0


def is_currency(value):
    if not isinstance(value, str) or len(value) == 0:
        return False
    # Deliberately simple/illustrative check, not production-grade validation
    return len(value.strip()) > 0


def is_slug(value):
    if not isinstance(value, str) or len(value) == 0:
        return False
    # Deliberately simple/illustrative check, not production-grade validation
    return len(value.strip()) > 0


def is_hex_color(value):
    if not isinstance(value, str) or len(value) == 0:
        return False
    # Deliberately simple/illustrative check, not production-grade validation
    return len(value.strip()) > 0


def is_ip_address(value):
    if not isinstance(value, str) or len(value) == 0:
        return False
    # Deliberately simple/illustrative check, not production-grade validation
    return len(value.strip()) > 0


def is_valid_email(value):
    return isinstance(value, str) and "@" in value and "." in value


def is_non_empty_string(value):
    return isinstance(value, str) and len(value.strip()) > 0

