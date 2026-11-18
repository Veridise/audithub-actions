"""Read explicitly mapped composite-action inputs without shell interpolation."""

import os
import re
from urllib.parse import urlsplit


def get_input(name: str, default: str = "", *, required: bool = False) -> str:
    value = os.environ.get("AH_" + name.upper().replace("-", "_"), default).strip()
    if required and not value:
        raise ValueError(f"The {name} input is required.")
    return value


def positive_integer(name: str, default: str = "") -> int:
    value = get_input(name, default, required=True)
    if not re.fullmatch(r"[0-9]+", value) or int(value) < 1:
        raise ValueError(f"The {name} input must be a positive integer.")
    return int(value)


def boolean(name: str, default: str = "false") -> bool:
    value = get_input(name, default).lower()
    if value not in {"true", "false"}:
        raise ValueError(f"The {name} input must be true or false.")
    return value == "true"


def https_url(name: str, default: str = "") -> str:
    value = get_input(name, default, required=True).rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or any(char.isspace() or ord(char) < 32 for char in value)
    ):
        raise ValueError(f"The {name} input must be an HTTPS URL without credentials or a query.")
    return value
