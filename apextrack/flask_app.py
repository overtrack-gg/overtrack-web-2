import logging
import os

import flask
import sentry_sdk
from flask import Flask, render_template
from flask_bootstrap import Bootstrap
from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration

from apextrack.data import CDN_URL, WELCOME_META
from apextrack.lib.authentication import check_authentication

app = Flask(__name__, template_folder='../templates', static_folder='../static')
bootstrap = Bootstrap(app)

if app.config['DEBUG']:
    # Fake login for dev
    @app.route('/fake_login')
    def fake_login():
        from flask import request
        from urllib import parse
        from overtrack_models.user import User
        from apextrack.lib.authentication import make_cookie
        from flask import Response
        base_hostname = parse.urlsplit(request.base_url).hostname
        if base_hostname not in ['127.0.0.1', 'localhost']:
            logging.error('/fake_login exposed on non-loopback device: FLASK_DEBUG should not be set on nonlocal deployments')
            return f'Refusing to serve /fake_login on nonlocal base URL: {base_hostname}', 403
        else:
            if 'username' in request.args:
                try:
                    user = User.username_index.get(request.args['username'])
                except User.DoesNotExist:
                    return 'User does not exist', 404
                else:
                    resp = Response(f'You are now authenticated as {user.username}')
                    resp.set_cookie(
                        'session',
                        make_cookie(user)
                    )
                    return resp
            else:
                return 'Please specify a username to authenticate as. Use ?username=...', 400

else:
    sentry_sdk.init(
        os.environ.get('SENTRY_DSN', 'https://077ec8ffb4404ce384ab84a5e6bc17ae@sentry.io/1450230'),
        integrations=[
            AwsLambdaIntegration()
        ],
        with_locals=True,
        debug=False
    )

    # Set up exception handling for running on lambda
    orig_handle_exception = app.handle_exception
    def handle_exception(e):
        sentry_sdk.capture_exception(e)
        return orig_handle_exception(e)
    app.handle_exception = handle_exception
    def unhandled_exceptions(e, event, context):
        sentry_sdk.capture_exception(e)
        return True

    # Fetch static assets from cloudfront instead of through the lambda
    orig_url_for = flask.url_for
    def url_for(endpoint, **values):
        if endpoint == 'static' and 'filename' in values:
            return CDN_URL + '/' + values['filename']
        else:
            return orig_url_for(endpoint, **values)
    app.jinja_env.globals['url_for'] = url_for
    flask.url_for = url_for


# Fancy logging for running locally
try:
    from overtrack.util.logging_config import config_logger
    config_logger(__name__, logging.INFO, False)
except ImportError:
    logging.basicConfig(level=logging.INFO)


# register context processors and filters
@app.context_processor
def inject_processors():
    from apextrack.lib.context_processors import processors
    return processors

from apextrack.lib.template_filters import filters
app.jinja_env.filters.update(filters)


# complex views requiring their own controllers
from apextrack.views.login import login_blueprint
app.register_blueprint(login_blueprint)

from apextrack.views.games_list import games_list_blueprint
app.register_blueprint(games_list_blueprint)

from apextrack.views.game import game_blueprint
app.register_blueprint(game_blueprint)

from apextrack.views.stats import results_blueprint
app.register_blueprint(results_blueprint, url_prefix='/stats')

try:
    from apextrack.views.discord_bot import discord_bot_blueprint
except:
    logging.exception('Failed to import discord_bot_blueprint - running without /discord_bot')
else:
    app.register_blueprint(discord_bot_blueprint, url_prefix='/discord_bot')

try:
    from apextrack.views.subscribe import subscribe_blueprint
except:
    logging.exception('Failed to import subscribe_blueprint - running without /subscribe')
else:
    app.register_blueprint(subscribe_blueprint, url_prefix='/subscribe')


# render the root page differently depending on logged in status
from apextrack.views.games_list import games_list

@app.route('/')
def root():
    if check_authentication() is None:
        return games_list()
    else:
        return welcome()


# template only views

@app.route('/client')
def client():
    return render_template('client.html', meta=WELCOME_META)

@app.route('/welcome')
def welcome():
    return render_template('welcome.html', meta=WELCOME_META)


# hack for streamer URLs
# TODO: replace when we have share links
from apextrack.views.games_list import render_games_list
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
