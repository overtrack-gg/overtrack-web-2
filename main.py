import logging
from datetime import datetime
from functools import wraps
from typing import Optional

import requests
from flask import Flask, Response, render_template, request
from flask import url_for as flask_url_for
from flask_bootstrap import Bootstrap
from werkzeug.utils import redirect

from api.authentication import require_authentication, check_authentication
from api.session import session
from blueprints.discord_bot import discord_bot_blueprint
from models.apex_game_summary import ApexGameSummary
from overtrack.util import s2ts

app = Flask(__name__)
bootstrap = Bootstrap(app)

logger = logging.getLogger(__name__)

app.register_blueprint(discord_bot_blueprint, url_prefix='/discord_bot')


def url_for(endpoint, **values):
    if endpoint == 'static' and 'filename' in values and values['filename'] not in ['style.css', 'map.js']:
        return 'https://d2igtsro72if25.cloudfront.net/1/' + values['filename']
    else:
        return flask_url_for(endpoint, **values)


app.jinja_env.globals['url_for'] = url_for


def require_login(_endpoint=None):
    def wrap(endpoint):
        @wraps(endpoint)
        def check_login(*args, **kwargs):
            if check_authentication() is None:
                return endpoint(*args, **kwargs)
            else:
                return redirect(url_for('login', next=request.url))

        return check_login

    if _endpoint is None:
        return wrap
    else:
        return wrap(_endpoint)


@app.template_filter()
def ifnone(v, o):
    if v is None:
        print(v, '>', o)
        return o
    else:
        return v


def to_ordinal(n: int) -> str:
    suffixes = {1: 'st', 2: 'nd', 3: 'rd'}
    i = n if n < 20 else n % 10
    return f'{n}{suffixes.get(i, "th")}'


def image_url(champ: Optional[str], large: bool = False) -> str:
    if large:
        return url_for('static', filename=f'images/{champ.lower()}_large.png' if champ else '')
    else:
        return url_for('static', filename=f'images/{champ.lower()}.png' if champ else 'images/unknown.png')


COLOURS = {
    'octane': '#486F3B',
    'mirage': '#D09B49',
    'bloodhound': '#AD2A33',
    'gibraltar': '#6B4B3C',
    'caustic': '#689122',
    'pathfinder': '#58859F',
    'wraith': '#5F439F',
    'bangalore': '#572C23',
    'lifeline': '#C243D8'
}
def champion_colour(champ: str) -> str:
    return COLOURS.get(champ.lower() if champ else None)


def strftime(t: float):
    dt = datetime.fromtimestamp(t)
    date = dt.strftime('%c').split(':', 1)[0].rsplit(' ', 1)[0]
    return date + ' ' + dt.strftime('%I:%M %p')


def duration(t: Optional[float]):
    if t is None:
        return '?'
    return s2ts(t).split(':', 1)[1]


base_context = {
    'to_ordinal': to_ordinal,
    's2ts': duration,
    'strftime': strftime,
    'image_url': image_url,
    'champion_colour': champion_colour,
}

@app.route('/login')
def login():
    if 'next' in request.args:
        next_ = request.args['next']
    else:
        next_ = request.host_url
    login_url = 'https://api2.overtrack.gg/login/twitch?next=' + next_
    return render_template(
        'login.html',
        login_url=login_url
    )


@app.route('/')
@app.route('/games')
@require_login
def games_list():
    return render_template(
        'games.html',
        games=ApexGameSummary.user_id_time_index.query(session.user_id, newest_first=True),
        **base_context
    )


@app.route('/game/<path:key>')
def game(key: str):
    summary = ApexGameSummary.get(key)
    logger.info(f'Fetching {summary.url}')
    r = requests.get(summary.url)
    if r.status_code == 404:
        return Response(
            "This isn't the game you're looking for",
            status=404
        )
    r.raise_for_status()
    game_data = r.json()

    # used for link previews
    og_title = f'{game_data["squad"]["player"]["name"]} placed #{summary.placed}'  # TODO: find another way of getting the name
    theme_color = {
        1: '#ffdf00',
        2: '#ef20ff',
        3: '#d95ff'
    }.get(summary.placed, '#992e26')
    og_description = f'{summary.kills} Kills'
    if summary.knockdowns:
        og_description += f'\n{summary.knockdowns} Knockdowns'
    if summary.squad_kills:
        og_description += f'\n{summary.squad_kills} Squad Kills'
    if summary.landed != 'Unknown':
        og_description += f'\nDropped {summary.landed}'

    return render_template(
        'game.html',
        summary=summary,
        game=game_data,

        og_title=og_title,
        theme_colour=theme_color,
        og_description=og_description,

        **base_context
    )


# TODO: support a summary in link previews for games lists


@app.route('/eeveea_')
def eeveea_games():
    return render_template(
        'games.html',
        games=ApexGameSummary.user_id_time_index.query(347766573, newest_first=True),
        **base_context
    )


@app.route("/by_key/<string:key>")
@require_authentication(superuser_required=True)
def games_by_key(key: str):
    return render_template(
        'games.html',
        games=ApexGameSummary.user_id_time_index.query(int(key), newest_first=True),
        **base_context
    )
