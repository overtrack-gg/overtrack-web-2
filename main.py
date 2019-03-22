import logging

from datetime import datetime
from functools import wraps

from flask import Flask, render_template, url_for
from flask_bootstrap import Bootstrap
from typing import Optional

from api.authentication import Authentication, require_authentication
from api.session import session
from models.apex_game_summary import ApexGameSummary
from overtrack.util import s2ts
from overtrack.util.logging_config import config_logger

app = Flask(__name__)
bootstrap = Bootstrap(app)

logger = logging.getLogger(__name__)

config_logger('apextrack-web', logging.INFO, False)


def to_ordinal(n: int) -> str:
    suffixes = {1: 'st', 2: 'nd', 3: 'rd'}
    i = n if n < 20 else n % 10
    return f'{n}{suffixes.get(i, "th")}'


def image_url(champ: Optional[str]) -> str:
    return url_for('static', filename=f'images/{champ.lower()}.png' if champ else 'images/unknown.png')


def strftime(t: float):
    dt = datetime.fromtimestamp(t)
    date = dt.strftime('%c').split(':', 1)[0].rsplit(' ', 1)[0]
    return date + ' ' + dt.strftime('%I:%M %p')


def duration(t: float):
    return s2ts(t).split(':', 1)[1]


@app.route("/")
@app.route("/games")
@require_authentication
def games_list():
    context = {
        'games': ApexGameSummary.user_id_time_index.query(session.user_id, newest_first=True),
        'to_ordinal': to_ordinal,
        's2ts': duration,
        'strftime': strftime,
        'image_url': image_url
    }
    return render_template('games.html', **context)


@app.route("/eeveea_")
def eeveea_games():
    context = {
        'games': ApexGameSummary.user_id_time_index.query(347766573, newest_first=True),
        'to_ordinal': to_ordinal,
        's2ts': duration,
        'strftime': strftime,
        'image_url': image_url
    }
    return render_template('games.html', **context)


@app.route("/by_key/<string:key>")
@require_authentication(superuser_required=True)
def games_by_key(key: str):
    context = {
        'games': ApexGameSummary.user_id_time_index.query(int(key), newest_first=True),
        'to_ordinal': to_ordinal,
        's2ts': duration,
        'strftime': strftime,
        'image_url': image_url
    }
    return render_template('games.html', **context)
