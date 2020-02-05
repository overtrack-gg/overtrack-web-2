import base64
import functools
import logging
import os
from typing import Tuple, List, NamedTuple

import requests
from flask import Flask, render_template, g, request
from flask_bootstrap import Bootstrap
from werkzeug.utils import redirect

from overtrack_web.flask_app import url_for

os.environ['HMAC_KEY'] = base64.b64encode(b'').decode()

from overtrack_web.data import WELCOME_META
from overtrack_web.data import Season, SEASONS
from overtrack_models.orm.apex_game_summary import ApexGameSummary

app = Flask(__name__, template_folder='../templates', static_folder='../static')
bootstrap = Bootstrap(app)

logging.basicConfig(level=logging.INFO)

# register context processors and filters
@app.context_processor
def inject_processors():
    from overtrack_web.lib.context_processors import processors

    return processors


# running locally - patch login/auth code
from overtrack_web.lib import authentication


class MockUser(NamedTuple):
    # TODO: this is poorly mocked out
    username: str = 'MOCK_USER'
    apex_last_season: int = list(SEASONS.values())[-1].index
    apex_last_game_ranked: bool = True
    apex_seasons: List[int] = list(SEASONS.keys())
    subscription_active: bool = True

    def refresh(self):
        pass

class MockSession(NamedTuple):
    user_id: int
    key: str
    superuser: bool = False
    user: MockUser = MockUser()

def mock_check_authentication(*_, **__):
    g.session = MockSession(
        user_id=-1,
        key='MOCK-USER'
    )
    return None

authentication.check_authentication = mock_check_authentication

# running locally - hack to load games from the API instead of from dynamodb
GAMES_SOURCE = os.environ.get('GAMES_SOURCE', 'mendokusaii')
import overtrack_web.views.apex.games_list
import overtrack_web.views.apex.stats
import overtrack_web.views.apex.game

def mock_get_games(user) -> Tuple[List[ApexGameSummary], bool, Season]:
    try:
        season_id = int(request.args['season'])
        is_ranked = request.args['ranked'].lower() == 'true'
    except:
        season_id = user.apex_last_season
        is_ranked = user.apex_last_game_ranked
    if season_id is None:
        season_id = 3
    season = SEASONS[season_id]

    games = []
    r = requests.get(f'https://api2.overtrack.gg/apex/games/{GAMES_SOURCE}?season={season_id}')
    r.raise_for_status()
    for g in r.json()['games']:
        games.append(ApexGameSummary(**g))

    return games, is_ranked, season

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
# old url: /game/...
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


share_redirects = {
    'mendokusaii': 'mendokusaii',
}
for key, username in share_redirects.items():
    route = functools.partial(redirect, f'/apex/games/{username}', code=308)
    route.__name__ = f'streamer_redirect_{key}'
    app.route('/' + key)(route)
