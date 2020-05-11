import string

from markupsafe import Markup

from overtrack_web.lib.context_processors import s2ts


def safeurl(s: str):
    """
    Escape all unsafe params EXCEPT '&' then mark as safe.

    This can be used to prevent a URL from being escaped when included in a template without having to mark the url as safe, which would
    allow attacks if the url contained the " or ' characters
    """
    return Markup(
        s
        .replace(">", "&gt;")
        .replace("<", "&lt;")
        .replace("'", "&#39;")
        .replace('"', "&#34;")
    )


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
        'valorant': 'Valorant',
    }[n]


filters = {
    'safeurl': safeurl,
    
    'ifnone': ifnone,
    's2ts': s2ts,
    'strip': strip,
    'game_name': game_name,
}
