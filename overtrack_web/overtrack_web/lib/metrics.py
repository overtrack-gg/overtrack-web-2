from typing import Optional, Dict

try:
    from api.util.metrics import *
except ImportError:
    def record(key: str, *, value: float = 1.0, unit: str = 'count') -> None:
        pass

    def event(title: str, text: str, tags: Optional[Dict[str, str]] = None) -> None:
        pass
