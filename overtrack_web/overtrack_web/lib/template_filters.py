import string

from overtrack_web.lib.context_processors import s2ts, duration


def ifnone(v, o):
    if v is None:
        return o
    else:
        return v


def strip(s, lowercase=False):
    if lowercase:
        s = s.lower()
    return ''.join(c for c in s if c in (string.digits + string.ascii_letters))


filters = {
    'ifnone': ifnone,
    's2ts': s2ts,
    'duration': duration,
    'strip': strip
}
