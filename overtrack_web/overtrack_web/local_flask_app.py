import base64
import logging
import os
from typing import Tuple, List, NamedTuple

import requests
from flask import Flask, render_template, g, request
from flask_bootstrap import Bootstrap

os.environ['HMAC_KEY'] = base64.b64encode(b'').decode()

from overtrack_web.data import WELCOME_META
from overtrack_web.data import Season, SEASONS
from overtrack_models.apex_game_summary import ApexGameSummary

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
from overtrack_web.lib.template_filters import filters
app.jinja_env.filters.update(filters)

from overtrack_web.views import games_list_blueprint
app.register_blueprint(games_list_blueprint)

from overtrack_web.views import game_blueprint
app.register_blueprint(game_blueprint)

from overtrack_web.views import results_blueprint
app.register_blueprint(results_blueprint, url_prefix='/stats')

from overtrack_web.views import games_list
@app.route('/')
def root():
    return games_list()


# template only views
@app.route('/client')
def client():
    return render_template('client.html', meta=WELCOME_META)

@app.route('/welcome')
def welcome():
    return render_template('welcome.html', meta=WELCOME_META)


# hack for streamer URLs
# TODO: replace when we have share links
from overtrack_web.views import render_games_list
from overtrack_models.user import User


@app.route('/eeveea_')
def eeveea_games():
    return render_games_list(User.user_id_index.get(347766573), make_meta=True, meta_title='eeveea_')


@app.route('/mendokusaii')
def mendokusaii_games():
    return render_games_list(User.user_id_index.get(-3), make_meta=True, meta_title='Mendokusaii')


@app.route('/heylauren')
def heylauren_games():
    return render_games_list(User.user_id_index.get(-420), make_meta=True, meta_title='heylauren')


@app.route('/shroud')
def shroud_games():
    return render_games_list(User.user_id_index.get(-400), make_meta=True, meta_title='Shroud')


@app.route('/diegosaurs')
def diegosaurs_games():
    return render_games_list(User.user_id_index.get(-401), make_meta=True, meta_title='Diegosaurs')


@app.route('/a_seagull')
def a_seagull_games():
    return render_games_list(User.user_id_index.get(-402), make_meta=True, meta_title='a_seagull')
