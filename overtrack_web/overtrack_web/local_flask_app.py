import base64
import logging
import os

import functools
from flask import Flask, g, render_template, request, url_for
from werkzeug.utils import redirect

os.environ['HMAC_KEY'] = base64.b64encode(b'').decode()

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.url_map.strict_slashes = False

try:
    from overtrack.util.logging_config import config_logger
    config_logger(__name__, logging.INFO, False)
except ImportError:
    logging.basicConfig(level=logging.INFO)

# Stop the app from reloading/initing twice
print("reloading", os.environ.get('WERKZEUG_RUN_MAIN'), os.environ)
if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
    raise ValueError()

# live building of scss
from sassutils.wsgi import SassMiddleware, Manifest
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

# port of https://bugs.python.org/issue34363 to the dataclasses backport
# see https://github.com/ericvsmith/dataclasses/issues/151
from overtrack_web.lib import dataclasses_asdict_namedtuple_patch
dataclasses_asdict_namedtuple_patch.patch()

# register context processors and filters
@app.context_processor
def inject_processors():
    from overtrack_web.lib.context_processors import processors as lib_context_processors
    processors = dict(lib_context_processors)
    # running locally - patch login/auth code
    from overtrack_web.mocks import login_mocks
    processors['user'] = login_mocks.mock_user
    return processors
from overtrack_web.lib.template_filters import filters
app.jinja_env.filters.update(filters)

# in local mode, content is all fetched over http - cache for lightning fast reloads
import requests_cache
requests_cache.install_cache('requests_cache')
import boto3
boto3.client = None

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

from overtrack_web.views.overwatch.game import game_blueprint as overwatch_game_blueprint
app.register_blueprint(overwatch_game_blueprint, url_prefix='/overwatch/games')


@app.route('/')
def root():
    return redirect(url_for('apex.games_list.games_list'), code=307)

# template only views
from overtrack_web.data import WELCOME_META
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
