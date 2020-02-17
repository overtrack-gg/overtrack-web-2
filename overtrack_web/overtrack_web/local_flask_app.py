import base64
import logging
import os

import functools
from urllib.request import Request

import flask
from flask import Flask, g, render_template, request, url_for
from werkzeug.utils import redirect

# port of https://bugs.python.org/issue34363 to the dataclasses backport
# see https://github.com/ericvsmith/dataclasses/issues/151
from overtrack_web.lib import dataclasses_asdict_namedtuple_patch
dataclasses_asdict_namedtuple_patch.patch()

request: Request = request

try:
    # Fancy logging when possible
    from overtrack.util.logging_config import config_logger
    config_logger(__name__, logging.INFO, False)
except ImportError:
    logging.basicConfig(level=logging.INFO)


# ------ FLASK SETUP AND CONFIG ------
app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.url_map.strict_slashes = False
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True


# ------ LOCAL DEV TWEAKS ------
# don't require HMAC_KEY to be defined for local dev
os.environ['HMAC_KEY'] = base64.b64encode(b'').decode()

# Stop the app from reloading/initing twice
print("reloading", os.environ.get('WERKZEUG_RUN_MAIN'), os.environ)
if os.environ.get('FLASK_DEBUG') is not None and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
    raise ValueError('Prevented reload')

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

# Force js to be unminified
orig_url_for = flask.url_for
def url_for(endpoint, **values):
    if endpoint == 'static' and 'filename' in values and values['filename'].endswith('.min.js'):
        values['filename'] = values['filename'][:-len('.min.js')] + '.js'
    return orig_url_for(endpoint, **values)
app.jinja_env.globals['url_for'] = url_for
flask.url_for = url_for

# in local mode, content is all fetched over http - cache for lightning fast reloads
import requests_cache
requests_cache.install_cache('requests_cache')
import boto3
boto3.client = None

# load and mock all games lists
from overtrack_web.mocks.apex_mocks import mock_apex_games
from overtrack_web.mocks.overwatch_mocks import mock_overwatch_games
mock_apex_games()
mock_overwatch_games()


# ------ JINJA2 TEMPLATE VARIABLES AND FILTERS ------
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


# ------ LOGIN/LOGOUT ------
# still needed in local mode to add "logout" button
from overtrack_web.views.login import login_blueprint
app.register_blueprint(login_blueprint)


# ------ APEX ------
from overtrack_web.views.apex.games_list import games_list_blueprint as apex_games_list_blueprint
app.register_blueprint(apex_games_list_blueprint, url_prefix='/apex/games')

from overtrack_web.views.apex.game import game_blueprint
app.register_blueprint(game_blueprint, url_prefix='/apex/games')

from overtrack_web.views.apex.stats import results_blueprint
app.register_blueprint(results_blueprint, url_prefix='/apex/stats')

from overtrack_web.views.apex.scrims import scrims_blueprint
app.register_blueprint(scrims_blueprint, url_prefix='/apex/scrims')


# ------ OVERWATCH ------
from overtrack_web.views.overwatch.games_list import games_list_blueprint as overwatch_games_list_blueprint
app.register_blueprint(overwatch_games_list_blueprint, url_prefix='/overwatch/games')

from overtrack_web.views.overwatch.game import game_blueprint as overwatch_game_blueprint
app.register_blueprint(overwatch_game_blueprint, url_prefix='/overwatch/games')


# ------ LEGACY PAGE REDIRECTS ------
@app.route('/game/<path:key>')
def game_redirect(key):
    from overtrack_models.orm.overwatch_game_summary import OverwatchGameSummary

    try:
        OverwatchGameSummary.get(key)
    except OverwatchGameSummary.DoesNotExist:
        return redirect(url_for('apex.game.game', key=key), code=308)
    else:
        return redirect(url_for('overwatch.game.game', key=key), code=308)

@app.route('/games/<string:key>')
def overwatch_share_link_redirect(key):
    return redirect(url_for('overwatch.games_list.shared_games_list', sharekey=key), code=308)

# redirect old apex.overtrack.gg/<streamer> shares
for key, username in {
    'mendokusaii': 'mendokusaii',
}.items():
    app.add_url_rule(
        f'/{key}',
        f'hardcoded_redirect_{key}',
        functools.partial(redirect, f'/apex/games/{username}', code=308)
    )

@app.route('/apex')
@app.route('/games')
def apex_games_redirect():
    return redirect(url_for('apex.games_list.games_list'), code=308)


# ------ ROOT PAGE  ------
@app.route('/')
def root():
    # Running locally - always logged in
    return redirect(url_for('apex.games_list.games_list'), code=307)


# ------ SIMPLE INFO PAGES  ------
from overtrack_web.data import WELCOME_META
@app.route('/client')
def client():
    return render_template('client.html', meta=WELCOME_META)

@app.route('/welcome')
def welcome():
    return render_template('welcome.html', meta=WELCOME_META)

@app.route('/discord')
def discord_redirect():
    return redirect('https://discord.gg/JywstAB')

