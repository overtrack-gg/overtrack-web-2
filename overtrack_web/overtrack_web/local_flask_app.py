import base64
import logging
import os
from typing import List, NamedTuple, Tuple

import flask
import functools
import requests
from flask import Flask, g, render_template, request, url_for
from flask_bootstrap import Bootstrap
from werkzeug.utils import redirect

os.environ['HMAC_KEY'] = base64.b64encode(b'').decode()

from overtrack_web.data.apex import SEASONS, Season, latest_season
from overtrack_web.data import WELCOME_META
from overtrack_models.orm.apex_game_summary import ApexGameSummary

# port of https://bugs.python.org/issue34363 to the dataclasses backport
# see https://github.com/ericvsmith/dataclasses/issues/151
from overtrack_web.lib import dataclasses_asdict_namedtuple_patch
dataclasses_asdict_namedtuple_patch.patch()

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.url_map.strict_slashes = False

logging.basicConfig(level=logging.INFO)

from sassutils.wsgi import SassMiddleware

# live building of scss
app.wsgi_app = SassMiddleware(app.wsgi_app, {
    'overtrack_web': ('../static/scss', '../static/css', '/static/css')
})
# this middleware wants css files to end with .scss.css, while boussole compiles to .css
orig_url_for = flask.url_for
def url_for(endpoint, **values):
    if endpoint == 'static' and 'filename' in values and values['filename'].endswith('.css'):
        values['filename'] = values['filename'].replace('.css', '.scss.css')
    return orig_url_for(endpoint, **values)
app.jinja_env.globals['url_for'] = url_for
flask.url_for = url_for

# running locally - patch login/auth code
from overtrack_web.lib import authentication
class MockUser(NamedTuple):
    # TODO: this is poorly mocked out
    username: str = 'MOCK_USER'
    apex_last_season: int = latest_season
    apex_last_game_ranked: bool = True
    apex_seasons: List[int] = list(SEASONS.keys())
    subscription_active: bool = True
    def refresh(self):
        pass
mock_user = MockUser()
class MockSession(NamedTuple):
    user_id: int
    key: str
    superuser: bool = False
    user: MockUser = mock_user
def mock_check_authentication(*_, **__):
    g.session = MockSession(
        user_id=-1,
        key='MOCK-USER'
    )
    return None
authentication.check_authentication = mock_check_authentication

# register context processors and filters
@app.context_processor
def inject_processors():
    from overtrack_web.lib.context_processors import processors as lib_context_processors
    from overtrack_web.lib.session import session
    processors = dict(lib_context_processors)
    def current_user():
        return mock_user
    processors['current_user'] = current_user
    return processors
from overtrack_web.lib.template_filters import filters
app.jinja_env.filters.update(filters)

# running locally - hack to load games from the API instead of from dynamodb
GAMES_SOURCE = os.environ.get('GAMES_SOURCE', 'mendokusaii')
import overtrack_web.views.apex.games_list
import overtrack_web.views.apex.stats
import overtrack_web.views.apex.game
class MockGamesIterator:
    def __init__(self, games, last_evaluated_key):
        self.games = games
        self.last_evaluated_key = last_evaluated_key
    def __iter__(self):
        return iter(self.games)
def mock_get_games(user, limit=100) -> Tuple[MockGamesIterator, bool, Season]:
    try:
        season_id = int(request.args['season'])
        is_ranked = request.args['ranked'].lower() == 'true'
    except:
        season_id = user.apex_last_season
        is_ranked = user.apex_last_game_ranked
    if season_id is None:
        season_id = latest_season
    season = SEASONS[season_id]
    games = []
    url = f'https://api2.overtrack.gg/apex/games/{GAMES_SOURCE}?season={season_id}&limit={limit}'
    logging.info(f'Fetching {url}')
    r = requests.get(url)
    r.raise_for_status()
    data = r.json()
    for g in data['games']:
        games.append(ApexGameSummary(**g))
    return MockGamesIterator(games, data['last_evaluated_key']), is_ranked, season
overtrack_web.views.apex.games_list.get_games = mock_get_games
def mock_get_games_stats(user):
    games = []
    r = requests.get(f'https://api2.overtrack.gg/apex/games/{GAMES_SOURCE}')
    r.raise_for_status()
    for g in r.json()['games']:
        games.append(ApexGameSummary(**g))
    return games
overtrack_web.views.apex.stats.get_games = mock_get_games_stats
def mock_get_summary(key):
    r = requests.get(f'https://api2.overtrack.gg/apex/game_summary/{key}')
    r.raise_for_status()
    return ApexGameSummary(**r.json())
overtrack_web.views.apex.game.get_summary = mock_get_summary

# complex views requiring their own controllers - slimmed down version from actual site
from overtrack_web.views.apex.login import login_blueprint
app.register_blueprint(login_blueprint)

from overtrack_web.views.apex.games_list import games_list_blueprint
app.register_blueprint(games_list_blueprint, url_prefix='/apex/games')
@app.route('/apex')
def apex_games_redirect():
    return redirect(url_for('apex_games_list.games_list'), code=308)

from overtrack_web.views.apex.game import game_blueprint
app.register_blueprint(game_blueprint, url_prefix='/apex/games')
@app.route('/game/<path:key>')
def apex_game_redirect(key):
    return redirect(url_for('apex_game.game', key=key), code=308)

@app.route('/')
def root():
    return redirect(url_for('apex_games_list.games_list'), code=307)

# template only views
@app.route('/client')
def client():
    return render_template('client.html', meta=WELCOME_META)

@app.route('/welcome')
def welcome():
    return render_template('welcome.html', meta=WELCOME_META)

@app.route('/logout')
def logout():
    return redirect('root')


share_redirects = {
    'mendokusaii': 'mendokusaii',
}
for key, username in share_redirects.items():
    route = functools.partial(redirect, f'/apex/games/{username}', code=308)
    route.__name__ = f'streamer_redirect_{key}'
    app.route('/' + key)(route)
