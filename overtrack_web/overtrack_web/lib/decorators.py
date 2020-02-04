import json
import logging
from datetime import datetime, timedelta
from functools import wraps
from typing import List, Optional
from urllib import parse

from flask import Response, make_response, request

logger = logging.getLogger(__name__)


ORIGIN_WHITELIST = [
    'www.overtrack.gg',
    'overtrack.gg',
    'apex.overtrack.gg',
    'dev.overtrack.gg',
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
            hostname = None
            if 'origin' in request.headers:
                logger.info(f'Got origin: ' + request.headers['origin'])

                hostname = parse.urlsplit(request.headers['origin']).hostname
            elif 'referer' in request.headers:
                logger.info(f'Got referer: ' + request.headers['referer'])
                hostname = parse.urlsplit(request.headers['referer']).hostname
            else:
                logger.info('Did not get origin or referer')

            if hostname:
                logger.info(f'Checking {hostname} against {whitelist or ORIGIN_WHITELIST}')
                if hostname in (whitelist or ORIGIN_WHITELIST):
                    logger.info('origin allowed - matches whitelist')
                    return endpoint(*args, **kwargs)
                elif allow_localhost and hostname in ['localhost', 'dev.localhost', '127.0.0.1']:
                    logger.info('origin allowed - matches localhost')
                    return endpoint(*args, **kwargs)

            logger.info('origin rejected')
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
