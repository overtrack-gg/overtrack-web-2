import base64
from typing import Union, Tuple

from flask import Response

FlaskResponse = Union[Response, Tuple[str, int], str]

def b64_encode(s: str) -> str:
    encoded = base64.urlsafe_b64encode(s.encode()).decode()
    return encoded.rstrip("=")


def b64_decode(s: str) -> str:
    padding = 4 - (len(s) % 4)
    s = s + ("=" * padding)
    return base64.urlsafe_b64decode(s.encode()).decode()


