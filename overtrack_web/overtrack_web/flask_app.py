import logging
import os
from urllib import parse

import flask
import functools
import sentry_sdk
from flask import Flask, Request, Response, make_response, render_template, request
from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration
from werkzeug.utils import redirect

from overtrack_web.data import CDN_URL, WELCOME_META
from overtrack_web.lib.authentication import check_authentication

# port of https://bugs.python.org/issue34363 to the dataclasses backport
# see https://github.com/ericvsmith/dataclasses/issues/151
from overtrack_web.lib import dataclasses_asdict_namedtuple_patch
dataclasses_asdict_namedtuple_patch.patch()

request: Request = request

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.url_map.strict_slashes = False

if app.config['DEBUG']:
    # live building of scss
    from sassutils.wsgi import SassMiddleware
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

    # Fake login for dev
    from overtrack_web.views.fake_login import fake_login_blueprint
    app.register_blueprint(fake_login_blueprint, url_prefix='/fake_login')

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


@app.after_request
def add_header(response):
    # response.cache_control.no_store = True
    if 'cache-control' not in response.headers:
        response.headers['cache-control'] = 'no-store'
    return response


@app.route('/test')
def test():
    import random
    from flask import render_template_string
    from flask import request

    return render_template_string('''
<html>
<body style="background-color: #%6x">
<p>{{ url_for('test') }}</p>
<p>{{ url_for('test', _external=True) }}</p>
<p>{{ url_for('game.apex_game', key='A') }}</p>
<p>{{ request.host }}</p>
<pre>%s</pre>
</body>
</html>
''' % (random.randint(0, 0xffffff), str(request.environ).replace(',', ',\n')))


# Fancy logging for running locally
try:
    from overtrack.util.logging_config import config_logger
    config_logger(__name__, logging.INFO, False)
except ImportError:
    logging.basicConfig(level=logging.INFO)


# register context processors and filters
@app.context_processor
def inject_processors():
    from overtrack_web.lib.context_processors import processors as lib_context_processors
    from overtrack_web.lib.session import session
    processors = dict(lib_context_processors)
    def current_user():
        if check_authentication() is None:
            return session.user
        else:
            return None
    processors['current_user'] = current_user
    return processors

from overtrack_web.lib.template_filters import filters
app.jinja_env.filters.update(filters)

# complex views requiring their own controllers
from overtrack_web.views.login import login_blueprint
app.register_blueprint(login_blueprint)

from overtrack_web.views.apex.games_list import games_list_blueprint
app.register_blueprint(games_list_blueprint, url_prefix='/apex/games')
@app.route('/apex')
@app.route('/games')
def apex_games_redirect():
    return redirect(url_for('apex_games_list.games_list'), code=308)

from overtrack_web.views.apex.game import game_blueprint
# old url: /game/...
app.register_blueprint(game_blueprint, url_prefix='/apex/games')
@app.route('/game/<path:key>')
def apex_game_redirect(key):
    return redirect(url_for('apex_game.game', key=key), code=308)


from overtrack_web.views.apex.stats import results_blueprint
# old url: /stats
app.register_blueprint(results_blueprint, url_prefix='/apex/stats')

from overtrack_web.views.apex.scrims import scrims_blueprint
app.register_blueprint(scrims_blueprint, url_prefix='/apex/scrims')

try:
    from overtrack_web.views.apex.discord_bot import discord_bot_blueprint
except:
    logging.exception('Failed to import discord_bot_blueprint - running without /discord_bot')
else:
    app.register_blueprint(discord_bot_blueprint, url_prefix='/apex/discord_bot')

try:
    from overtrack_web.views.subscribe import subscribe_blueprint
except:
    logging.exception('Failed to import subscribe_blueprint - running without /subscribe')
else:
    app.register_blueprint(subscribe_blueprint, url_prefix='/subscribe')


# render the root page differently depending on logged in status
@app.route('/')
def root():
    if check_authentication() is None:
        return redirect(url_for('apex_games_list.games_list'), code=307)
    else:
        return welcome()


# template only views

@app.route('/client')
def client():
    return render_template('client.html', meta=WELCOME_META)

@app.route('/welcome')
def welcome():
    return render_template('welcome.html', meta=WELCOME_META)


@app.route('/discord')
def discord_redirect():
    return redirect('https://discord.gg/JywstAB')


@app.route('/logout')
def logout():
    response: Response = make_response(redirect(url_for('root')))
    domain = parse.urlsplit(request.url).hostname

    # remove non-domain specific cookie
    response.set_cookie('session', '', expires=0)

    # remove domain specific cookie for this domain
    response.set_cookie('session', '', expires=0, domain=domain)

    if any(c not in '.0123456789' for c in domain):
        # not an IP address - remove cookie for subdomains of this domain
        response.set_cookie('session', '', expires=0, domain='.' + domain)
        if domain.count('.') >= 2:
            # we are on a subdomain - remove cookie for this and all other subdomains
            response.set_cookie('session', '', expires=0, domain='.' + domain.split('.', 1)[-1])

    return response


share_redirects = {
    'mendokusaii': 'mendokusaii',
}
for key, username in share_redirects.items():
    route = functools.partial(redirect, f'/apex/games/{username}', code=308)
    route.__name__ = f'streamer_redirect_{key}'
    app.route('/' + key)(route)

# @app.route('/eeveea_')
# def eeveea_games():
#     return render_games_list(User.user_id_index.get(347766573), public=True, meta_title='eeveea_')
#
# @app.route('/mendokusaii')
# def mendokusaii_games():
#     return render_games_list(User.user_id_index.get(-3), public=True, meta_title='Mendokusaii')
#
# @app.route('/heylauren')
# def heylauren_games():
#     return render_games_list(User.user_id_index.get(-420), public=True, meta_title='heylauren')
#
# @app.route('/shroud')
# def shroud_games():
#     return render_games_list(User.user_id_index.get(-400), public=True, meta_title='Shroud')
#
# @app.route('/diegosaurs')
# def diegosaurs_games():
#     return render_games_list(User.user_id_index.get(-401), public=True, meta_title='Diegosaurs')
#
# @app.route('/a_seagull')
# def a_seagull_games():
#     return render_games_list(User.user_id_index.get(-402), public=True, meta_title='a_seagull')
