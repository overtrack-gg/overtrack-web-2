import base64
import json
import logging
import os
import time
from functools import wraps
from typing import Optional, Union
from urllib.parse import urlparse

import jwt
import sentry_sdk
from flask import Blueprint, Flask, Response, g, request, url_for
from werkzeug.utils import redirect

from apextrack.session import Session, _user_cache
from models.user import User

API_PATH = os.environ.get('API_PATH', 'https://api.overtrack.gg')
HMAC_KEY = base64.b64decode(os.environ['HMAC_KEY'])
SESSION_EXPIRE_TIME = 4 * 30 * 24 * 60 * 60

logger = logging.getLogger(__name__)

request = request
""" :type request: flask.Request """


class Authentication:
    """
    Mixin for requiring authentication on an entire app/blueprint.
    This is intended for API access as non-user-friendly responses will be returned.
    """

    def __init__(self, app: Union[Flask, Blueprint], audience='webapp', superuser_required=False, check_user=False):
        self.audience = audience
        self.superuser_required = superuser_required
        self.check_user = check_user
        self.init_app(app)

    def init_app(self, app: Flask):
        def before_request():
            g.scope_manager = sentry_sdk.push_scope()
            g.scope = g.scope_manager.__enter__()
            return check_authentication(self.audience, self.superuser_required, self.check_user)

        def after_request(resp):
            if 'scope_manager' in g:
                g.scope_manager.__exit__(None, None, None)
            return resp

        app.before_request(before_request)
        app.after_request(after_request)


def require_authentication(_endpoint=None, *, allow_audience: str = 'webapp', superuser_required: bool = False, check_user: bool = False):
    """
    Decorator for requiring authentication on a single endpoint.
    This is intended for API access as non-user-friendly responses will be returned.
    """
    def wrap(endpoint):
        @wraps(endpoint)
        def check_auth(*args, **kwargs):
            with sentry_sdk.push_scope() as scope:
                g.scope = scope
                r = check_authentication(allow_audience, superuser_required, check_user)
                if r:
                    return r
                return endpoint(*args, **kwargs)

        return check_auth

    if _endpoint is None:
        # called as @require_login()
        return wrap
    else:
        # called as @require_login
        return wrap(_endpoint)


class Login:
    """
    Mixin for requiring login on an entire app/blueprint.
    Unlike Authentication, this will redirect the user to a login page and return them to the original page once login is complete.
    """

    def __init__(self, app: Union[Flask, Blueprint], check_user=False):
        self.check_user = check_user
        self.init_app(app)

    def init_app(self, app: Flask):
        def before_request():
            g.scope_manager = sentry_sdk.push_scope()
            g.scope = g.scope_manager.__enter__()
            if check_authentication(check_user=self.check_user):
                return redirect(url_for('login.login_root', next=request.url))

        def after_request(resp):
            if 'scope_manager' in g:
                g.scope_manager.__exit__(None, None, None)
            return resp

        app.before_request(before_request)
        app.after_request(after_request)


def require_login(_endpoint=None, check_user: bool = False):
    """
    Decorator for requiring authentication on a single endpoint.
    Unlike require_authentication, this decorator will redirect the user to a login page and return them to the original page once login is complete.
    """
    def wrap(endpoint):
        @wraps(endpoint)
        def check_login(*args, **kwargs):
            if check_authentication(check_user=check_user) is None:
                return endpoint(*args, **kwargs)
            else:
                return redirect(url_for('login.login_root', next=request.url))

        return check_login

    if _endpoint is None:
        return wrap
    else:
        return wrap(_endpoint)


def check_authentication(allow_audience: str = 'webapp', superuser_required: bool = False, check_user: bool = False) -> Optional[Response]:
    if 'scope' in g:
        funclocal_scope_manager = None
        scope = g.scope
    else:
        funclocal_scope_manager = sentry_sdk.push_scope()
        scope = funclocal_scope_manager.__enter__()

    session = request.cookies.get('session')
    if not session:
        logger.info(f'No session found')
        return make_error('No session found')

    scope.set_extra('session_cookie', session)

    try:
        user_data = jwt.decode(session, HMAC_KEY, algorithms=['HS256'], audience=allow_audience)
    except jwt.InvalidTokenError as e:
        s = session
        try:
            s = jwt.decode(session, verify=False)
        except:
            pass
        logger.warning(f'JWT token {s} invalid: {e}')
        sentry_sdk.capture_message('JWT token invalid')
        return make_error(f'{e}')
    else:
        user = None
        if check_user:
            try:
                user = User.user_id_index.get(user_data['user-id'])
                _user_cache[user.key] = user
            except User.DoesNotExist:
                logger.error(f'Got valid session token, but user did not exist')
                return make_error('User invalid')

        if superuser_required and not user_data.get('superuser', False):
            logger.warning(f'Got session: {user_data}, but required superuser=True')
            sentry_sdk.capture_message('Got non-superuser session for endpoint with superuser_required')
            return make_error('Not superuser', 403)

        logger.info(f'Session valid for {user_data}')
        key = user_data.get('key')
        if not key:
            logger.warning(f'Got old style session (battletag instead of key)')
            key = user_data['battletag']
        g.session = Session(
            user_id=user_data['user-id'],
            key=key,
            superuser=user_data.get('superuser', False),
        )

        scope.user = {'id': g.session.user_id, 'username': g.session.lazy_username}
        scope.set_extra('session', g.session)
        if funclocal_scope_manager:
            funclocal_scope_manager.__exit__(None, None, None)

        try:
            segment = xray_recorder.current_segment()
            segment.put_annotation('user_id', user.user_id if user else user_data['user-id'])
            segment.put_annotation('user_key', user.key if user else key)
            if user:
                segment.put_annotation('user_name', user.username)
        except:
            pass

        return None


def make_cookie(user: User, audience: str = 'webapp', expiry: Optional[int] = SESSION_EXPIRE_TIME) -> str:
    now = int(time.time())
    data = {
        'key': user.key,
        'user-id': user.user_id,
        'superuser': user.superuser,

        'iat': now,
        'aud': audience,
    }
    if expiry:
        data['exp'] = now + expiry
    return jwt.encode(data, HMAC_KEY, algorithm='HS256').decode()


def make_error(reason: str, status=401) -> Response:
    return Response(
        response=json.dumps({
            'message': 'Forbidden: %s' % reason,
            'authenticate_url': f'https://api2.overtrack.gg/login',
            'redirect': f'https://api2.overtrack.gg/login?next={request.url}'
        }),
        status=status,
        mimetype='application/json'
    )


ORIGIN_WHITELIST = [
    'localhost',
    'dev.localhost',
    '127.0.0.1',

    'overtrack.gg',
    'www.overtrack.gg',
    'apex.overtrack.gg',
    'apex-beta.overtrack.gg',
    'apex.overtrack.gg',
    'api2.overtrack.gg',
    'api.overtrack.gg'
]
def require_origin(_endpoint=None, origins=tuple(ORIGIN_WHITELIST), origin_required=True, or_refererer=False):
    def allowed_origin(origin: str) -> bool:
        host = urlparse(request.host_url).netloc.split(':')[0]
        return host in origins

    def wrap(endpoint):
        @wraps(endpoint)
        def check_origin(*args, **kwargs):
            origin = request.environ.get('HTTP_ORIGIN')
            if not origin and or_refererer:
                origin = request.referrer

            if origin_required and not origin:
                return Response(
                    'Did not get origin',
                    status=400
                )
            elif not origin_required and not origin:
                # can't have the wrong origin if you don't have an origin WeSmart
                return endpoint(*args, **kwargs)
            elif allowed_origin(origin):
                return endpoint(*args, **kwargs)
            else:
                return Response(
                    'origin not whitelisted',
                    status=400
                )

        return check_origin

    if _endpoint is None:
        return wrap
    else:
        return wrap(_endpoint)


def main() -> None:
    print(make_cookie(
        User.get('GMoxFr#2684'),
    ))


if __name__ == '__main__':
    main()
