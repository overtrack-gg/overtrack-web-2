from typing import Optional, Dict

try:
    from api.util.metrics import record as _record, event as _event

    def record(key: str, *, value: float = 1.0, unit: str = 'count') -> None:
        _record(key, value=value, unit=unit)

    def event(title: str, text: str, tags: Optional[Dict[str, str]] = None) -> None:
        _event(title, text, tags, stack='overtrack-web-2')

except ImportError:
    def record(key: str, *, value: float = 1.0, unit: str = 'count') -> None:
        pass

    def event(title: str, text: str, tags: Optional[Dict[str, str]] = None) -> None:
        pass
