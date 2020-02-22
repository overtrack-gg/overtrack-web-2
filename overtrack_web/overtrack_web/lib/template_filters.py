import string

from overtrack_web.lib.context_processors import s2ts


def ifnone(v, o):
    if v is None:
        return o
    else:
        return v


def strip(s, lowercase=False):
    if lowercase:
        s = s.lower()
    return ''.join(c for c in s if c in (string.digits + string.ascii_letters))


def game_name(n: str) -> str:
    return {
        'apex': 'Apex Legends',
        'overwatch': 'Overwatch',
    }[n]


filters = {
    'ifnone': ifnone,
    's2ts': s2ts,
    'strip': strip,
    'game_name': game_name,
}
