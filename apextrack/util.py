import datetime
from typing import Optional


def strftime(t: float):
    dt = datetime.datetime.fromtimestamp(t)
    date = dt.strftime('%c').split(':', 1)[0].rsplit(' ', 1)[0]
    # return date + ' ' +
    return dt.strftime('%I:%M %p')


def duration(t: Optional[float]):
    if t is None:
        return '?'
    return s2ts(t).split(':', 1)[1]


def s2ts(s: float, ms: bool = False, zpad: bool = True) -> str:
    sign = ''
    if s < 0:
        sign = '-'
        s = -s
    m = s / 60
    h = m / 60
    if zpad or int(h):
        ts = '%s%02d:%02d:%02d' % (sign, h, m % 60, s % 60)
    else:
        ts = '%s%02d:%02d' % (sign, m % 60, s % 60)
    if ms:
        return ts + f'{s % 1 :1.3f}'[1:]
    else:
        return ts
