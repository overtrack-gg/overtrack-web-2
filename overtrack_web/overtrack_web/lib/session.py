import json
from typing import NamedTuple

import typedload
from flask import g
from sentry_sdk.serializer import add_global_repr_processor
from werkzeug.local import LocalProxy

from overtrack_models.user import User

_user_cache = {}

class Session(NamedTuple):
    user_id: int
    key: str
    superuser: bool = False

    @property
    def user(self) -> User:
        if self.key in _user_cache:
            return _user_cache[self.key]
        else:
            user = User.user_id_index.get(self.user_id)
            _user_cache[self.key] = user
            return user

    @property
    def username(self) -> str:
        return self.user.username.replace('#', '-')

    @property
    def lazy_username(oself):
        class LazyUsername:
            def __str__(self) -> str:
                return oself.username
            __repr__ = __str__
        return LazyUsername()

    def to_json(self) -> str:
        return json.dumps(typedload.dump(self))


session: Session = LocalProxy(lambda: g.session)


@add_global_repr_processor
def processor(value, hint):
    if isinstance(value, Session):
        data = typedload.dump(value)

        def jsonsafe(v):
            if isinstance(v, set):
                return list(v)
            return v

        return {
            'user -> ': {
                k: jsonsafe(v)
                for k, v in value.user.asdict().items()
            },
            **data
        }
    return NotImplemented
