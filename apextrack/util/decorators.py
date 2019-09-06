import json
from datetime import datetime, timedelta
from functools import wraps
from typing import List, Optional
from urllib import parse

from flask import make_response, Response, request

ORIGIN_WHITELIST = [
    '05vtsqqgd3.execute-api.us-west-2.amazonaws.com',
    'owyr1hktg5.execute-api.us-west-2.amazonaws.com',
    'overtrack.gg',
    'apex.overtrack.gg',
    'api.overtrack.gg',
    'api2.overtrack.gg'
]


def cache_control(hours=1, seconds: int = None):
    """ Flask decorator that sets Expire and Cache headers """

    def fwrap(f):
        @wraps(f)
        def wrapped_f(*args, **kwargs):
            rsp = make_response(f(*args, **kwargs))
            if seconds:
                then = datetime.now() + timedelta(seconds=seconds)
            else:
                then = datetime.now() + timedelta(hours=hours)
            rsp.headers.add('Expires', then.strftime('%a, %d %b %Y %H:%M:%S GMT'))
            rsp.headers.add('Cache-Control', 'public,max-age=%d' % int(3600 * hours))
            return rsp

        return wrapped_f

    return fwrap


def restrict_origin(_endpoint=None, *, whitelist: Optional[List[str]] = None, allow_localhost: bool = True):
    """
    Decorator for requiring the request's origin to match a specified or default whitelist.
    """

    def wrap(endpoint):
        @wraps(endpoint)
        def check_origin(*args, **kwargs):
            if 'origin' in request.headers:
                hostname = parse.urlsplit(request.headers['origin']).hostname
                if hostname in (whitelist or ORIGIN_WHITELIST):
                    return endpoint(*args, **kwargs)
                elif allow_localhost and hostname in ['localhost', 'dev.localhost', '127.0.0.1']:
                    return endpoint(*args, **kwargs)

            return Response(
                json.dumps({
                    'message': 'origin disallowed'
                }),
                content_type='application/json',
                status=400
            )

        return check_origin

    if _endpoint is None:
        # called as @restrict_origin()
        return wrap
    else:
        # called as @restrict_origin
        return wrap(_endpoint)
