import base64
import logging
import os
from typing import List, NamedTuple, Tuple

import flask
import functools
import requests
from flask import Flask, g, render_template, request, url_for
from werkzeug.utils import redirect

os.environ['HMAC_KEY'] = base64.b64encode(b'').decode()

from overtrack_web.data.apex_data import seasons, ApexSeason, current_season
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
from sassutils.wsgi import SassMiddleware, Manifest
# noinspection PyTypeChecker
app.wsgi_app = SassMiddleware(
    app.wsgi_app,
    {
        'overtrack_web': Manifest(
            '../static/scss',
            '../static/css',
            '/static/css',
            strip_extension=True,
        )
    }
)

# running locally - patch login/auth code
from overtrack_web.mocks import login_mocks

# register context processors and filters
@app.context_processor
def inject_processors():
    from overtrack_web.lib.context_processors import processors as lib_context_processors
    processors = dict(lib_context_processors)
    processors['user'] = login_mocks.mock_user
    return processors
from overtrack_web.lib.template_filters import filters
app.jinja_env.filters.update(filters)

# running locally - hack to load games from the API instead of from dynamodb
from overtrack_web.mocks.apex_mocks import mock_apex_games
mock_apex_games()
from overtrack_web.mocks.overwatch_mocks import mock_overwatch_games
mock_overwatch_games()

# complex views requiring their own controllers - slimmed down version from actual site
from overtrack_web.views.login import login_blueprint
app.register_blueprint(login_blueprint)

# ------ APEX ROUTING ------
from overtrack_web.views.apex.games_list import games_list_blueprint
app.register_blueprint(games_list_blueprint, url_prefix='/apex/games')
@app.route('/apex')
def apex_games_redirect():
    return redirect(url_for('apex.games_list.games_list'), code=308)

from overtrack_web.views.apex.game import game_blueprint
app.register_blueprint(game_blueprint, url_prefix='/apex/games')
@app.route('/game/<path:key>')
def apex_game_redirect(key):
    return redirect(url_for('apex_game.game', key=key), code=308)

from overtrack_web.views.apex.stats import results_blueprint
app.register_blueprint(results_blueprint, url_prefix='/apex/stats')

# ------ OVERWATCH ROUTING ------
from overtrack_web.views.overwatch.games_list import games_list_blueprint as overwatch_games_list_blueprint
app.register_blueprint(overwatch_games_list_blueprint, url_prefix='/overwatch/games')


@app.route('/')
def root():
    return redirect(url_for('apex.games_list.games_list'), code=307)

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
