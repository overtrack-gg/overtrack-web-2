import datetime
from typing import Optional

from flask import url_for
from jinja2 import Undefined
from werkzeug.routing import BuildError


def url_exists(*args):
    try:
        url_for(*args)
    except BuildError:
        return False
    else:
        return True


def image_url(champ: Optional[str], large: bool = False) -> str:
    if large:
        return url_for('static', filename=f'images/apex/{champ.lower()}_large.png' if champ else '')
    else:
        return url_for('static', filename=f'images/apex/{champ.lower()}.png' if champ else 'images/apex/unknown.png')


COLOURS = {
    'octane': '#486F3B',
    'mirage': '#D09B49',
    'bloodhound': '#AD2A33',
    'gibraltar': '#6B4B3C',
    'caustic': '#689122',
    'pathfinder': '#58859F',
    'wraith': '#5F439F',
    'bangalore': '#572C23',
    'lifeline': '#C243D8',
    'loba': '#A44D39',
    'rampart': '#FF51BE'
}


def champion_colour(champ: str) -> str:
    return COLOURS.get(champ.lower() if champ else None)


def format_rp(v: Optional[int]):
    if isinstance(v, Undefined):
        return ''
    elif v is None:
        return '?'
    elif v == 0:
        return '+0'
    else:
        return f'{v:+}'


def to_ordinal(n: int) -> str:
    suffixes = {1: 'st', 2: 'nd', 3: 'rd'}
    i = n if n < 20 else n % 10
    return f'{n}{suffixes.get(i, "th")}'


def strftime(t: float):
    dt = datetime.datetime.fromtimestamp(t)
    date = dt.strftime('%c').split(':', 1)[0].rsplit(' ', 1)[0]
    # return date + ' ' +
    return dt.strftime('%I:%M %p')


def s2ts(s: float, ms: bool = False, zpad: bool = False) -> str:
    sign = ''
    if s < 0:
        sign = '-'
        s = -s
    m = s / 60
    h = m / 60
    if zpad or int(h):
        ts = '%s%02d:%02d:%02d' % (sign, h, m % 60, s % 60)
    else:
        ts = '%s%2d:%02d' % (sign, m % 60, s % 60)
    if ms:
        return ts + f'{s % 1 :1.3f}'[1:]
    else:
        return ts


def ticks(start, stop, nbins=10, steps=(1, 3, 6, 10), prune='upper'):
    from overtrack_web.vendor.matplotlib.ticker import MaxNLocator
    return MaxNLocator(nbins=nbins, steps=steps, prune=prune).tick_values(start, stop)


processors = {
    'url_exists': url_exists,

    'to_ordinal': to_ordinal,
    's2ts': s2ts,
    'duration': s2ts,
    'strftime': strftime,
    'image_url': image_url,
    'champion_colour': champion_colour,
    'format_rp': format_rp,
    'repr': repr,

    'ticks': ticks,
}
