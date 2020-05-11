import base64
from typing import Union, Tuple, Optional
from urllib.parse import parse_qs, urlparse

from flask import Response
from werkzeug.datastructures import MultiDict

from overtrack_web.lib.session import session

FlaskResponse = Union[Response, Tuple[str, int], str]

def b64_encode(s: str) -> str:
    encoded = base64.urlsafe_b64encode(s.encode()).decode()
    return encoded.rstrip("=")


def b64_decode(s: str) -> str:
    padding = 4 - (len(s) % 4)
    s = s + ("=" * padding)
    return base64.urlsafe_b64decode(s.encode()).decode()


def check_superuser() -> bool:
    from overtrack_web.lib.authentication import check_authentication
    if check_authentication() is None:
        return session.user.superuser
    else:
        return False


def hopeful_int(s: Optional[str]) -> Optional[int]:
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def parse_args(url: Optional[str]) -> MultiDict:
    if not url:
        return MultiDict()
    return MultiDict(parse_qs(urlparse(url).query))
