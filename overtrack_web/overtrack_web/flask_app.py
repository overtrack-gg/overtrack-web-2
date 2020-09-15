import functools
import logging
import os

import flask
import sentry_sdk
from flask import Flask, Request, render_template, request, url_for, render_template_string
from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration
from werkzeug.utils import redirect

from overtrack_web.data import CDN_URL, WELCOME_META
from overtrack_web.lib.authentication import check_authentication, require_login

# port of https://bugs.python.org/issue34363 to the dataclasses backport
# see https://github.com/ericvsmith/dataclasses/issues/151
from overtrack_web.lib import dataclasses_asdict_namedtuple_patch
from overtrack_web.lib.session import session
from overtrack_web.views.sitemap import sitemap_blueprint

dataclasses_asdict_namedtuple_patch.patch()

LOG_FORMAT = '[%(asctime)16s | %(levelname)8s | %(filename)s:%(lineno)s %(funcName)s() ] %(message)s'


request: Request = request
logger = logging.getLogger(__name__)


# ------ FLASK SETUP AND CONFIG ------
app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.url_map.strict_slashes = False
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True

@app.after_request
def add_default_no_cache_header(response):
    # response.cache_control.no_store = True
    if 'cache-control' not in response.headers:
        response.headers['cache-control'] = 'no-store'
    return response


# ------ FLASK DEBUG vs. LIVE CONFIG ------
if app.config['DEBUG']:
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

    # Fake login for dev
    from overtrack_web.views.fake_login import fake_login_blueprint
    app.register_blueprint(fake_login_blueprint, url_prefix='/fake_login')

    # Force js to be unminified
    orig_url_for = flask.url_for
    def url_for(endpoint, **values):
        if endpoint == 'static' and 'filename' in values and values['filename'].endswith('.min.js'):
            values['filename'] = values['filename'][:-len('.min.js')] + '.js'
        return orig_url_for(endpoint, **values)
    app.jinja_env.globals['url_for'] = url_for
    flask.url_for = url_for

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

    # Fetch static assets from cdn instead of through the lambda
    orig_url_for = flask.url_for
    def url_for(endpoint, **values):
        if endpoint == 'static' and 'filename' in values:
            return CDN_URL + '/' + values['filename']
        else:
            return orig_url_for(endpoint, **values)
    app.jinja_env.globals['url_for'] = url_for
    flask.url_for = url_for


# ------ JINJA2 TEMPLATE VARIABLES AND FILTERS ------
@app.context_processor
def context_processor():
    from overtrack_web.lib.context_processors import processors as lib_context_processors
    from overtrack_web.lib.session import session
    processors = dict(lib_context_processors)
    processors['user'] = session.user if check_authentication() is None else None
    return processors
from overtrack_web.lib.template_filters import filters
app.jinja_env.filters.update(filters)


# ------ LOGIN/LOGOUT ------
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

try:
    # support running even if the discord bot fails (e.g. missing env vars, fails to fetch cache of enabled bots)
    from overtrack_web.views.apex.discord_bot import apex_discord_blueprint
except:
    logging.exception('Failed to import apex_discord_bot - running without /apex/discord_bot')
else:
    app.register_blueprint(apex_discord_blueprint, url_prefix='/apex/discord_bot')


# ------ VALORANT ------
from overtrack_web.views.valorant.games_list import games_list_blueprint as valorant_games_list_blueprint
app.register_blueprint(valorant_games_list_blueprint, url_prefix='/valorant/games')

from overtrack_web.views.valorant.game import game_blueprint as valorant_game_blueprint
app.register_blueprint(valorant_game_blueprint, url_prefix='/valorant/games')

try:
    from overtrack_web.views.valorant.stats import stats_blueprint as valorant_stats_blueprint
    app.register_blueprint(valorant_stats_blueprint, url_prefix='/valorant/winrates')
except:
    logger.error('Failed to import valorant winrates')

try:
    # support running even if the discord bot fails (e.g. missing env vars, fails to fetch cache of enabled bots)
    from overtrack_web.views.valorant.notifications import valorant_notifications_blueprint
except:
    logging.exception('Failed to import valorant_notifications_blueprint - running without /valorant/notifications')
else:
    app.register_blueprint(valorant_notifications_blueprint, url_prefix='/valorant/notifications')


# ------ OVERWATCH ------
from overtrack_web.views.overwatch.games_list import games_list_blueprint as overwatch_games_list_blueprint
app.register_blueprint(overwatch_games_list_blueprint, url_prefix='/overwatch/games')

from overtrack_web.views.overwatch.game import game_blueprint as overwatch_game_blueprint
app.register_blueprint(overwatch_game_blueprint, url_prefix='/overwatch/games')

from overtrack_web.views.overwatch.hero_stats import hero_stats_blueprint
app.register_blueprint(hero_stats_blueprint, url_prefix='/overwatch/hero_stats')

try:
    # support running even if the discord bot fails (e.g. missing env vars, fails to fetch cache of enabled bots)
    from overtrack_web.views.overwatch.discord_bot import overwatch_discord_blueprint
except:
    logging.exception('Failed to import overwatch_discord_bot - running without /overwatch/discord_bot')
else:
    app.register_blueprint(overwatch_discord_blueprint, url_prefix='/overwatch/discord_bot')


# ------ LEGACY PAGE REDIRECTS ------
@app.route('/game/<path:key>')
def game_redirect(key):
    from overtrack_models.orm.overwatch_game_summary import OverwatchGameSummary
    try:
        OverwatchGameSummary.get(key)
    except OverwatchGameSummary.DoesNotExist:
        return redirect(url_for('apex.game.game', key=key), code=301)
    else:
        return redirect(url_for('overwatch.game.game', key=key), code=301)

@app.route('/games/<string:key>')
def overwatch_share_link_redirect(key):
    return redirect(url_for('overwatch.games_list.shared_games_list', sharekey=key), code=301)

# redirect old apex.overtrack.gg/<streamer> shares
for key, username in {
    'mendokusaii': 'mendokusaii',
}.items():
    app.add_url_rule(
        f'/{key}',
        f'hardcoded_redirect_{key}',
        functools.partial(redirect, f'/apex/games/{username}', code=301)
    )

@app.route('/apex')
def apex_games_redirect():
    return redirect(url_for('apex.games_list.games_list'), code=301)
@app.route('/overwatch')
def overwatch_games_redirect():
    return redirect(url_for('overwatch.games_list.games_list'), code=301)
@app.route('/valorant')
def valorant_games_redirect():
    return redirect(url_for('valorant.games_list.games_list'), code=301)


@app.route('/assets/<path:path>')
def legacy_assets(path):
    return redirect('https://old.overtrack.gg/assets/' + path, code=301)

@app.route('/assets/<string:key>.jpg')
def legacy_assets_banner(key):
    return redirect('https://old.overtrack.gg/' + key + '.jpg', code=301)

@app.route('/favicon.png')
def favicon():
    return redirect(url_for('static', filename='images/favicon.png'), code=301)


# ------ SUBSCRIBE  ------
try:
    from overtrack_web.views.subscribe import subscribe_blueprint
except:
    logging.exception('Failed to import subscribe_blueprint - running without /subscribe')
else:
    app.register_blueprint(subscribe_blueprint, url_prefix='/subscribe')


# ------ ROOT PAGE  ------
@app.route('/')
def root():
    if check_authentication() is None:
        return games()
    else:
        return welcome()


@app.route('/games')
@require_login
def games():
    if session.user.overwatch_games and not session.user.apex_games and not session.user.valorant_games:
        logger.info(f'User has overwatch games and no apex/valorant games, redirecting to overwatch games list')
        return redirect(url_for('overwatch.games_list.games_list'), code=302)
    elif session.user.apex_games and not session.user.overwatch_games and not session.user.valorant_games:
        logger.info(f'User has apex games and no overwatch/valorant games, redirecting to apex games list')
        return redirect(url_for('apex.games_list.games_list'), code=302)
    elif session.user.valorant_games and not session.user.overwatch_games and not session.user.apex_games:
        logger.info(f'User has valorant games and no overwatch/apex games, redirecting to valorant games list')
        return redirect(url_for('valorant.games_list.games_list'), code=302)
    elif not session.user.overwatch_games and session.user.apex_games and not session.user.valorant_games:
        logger.info(f'User has no apex games and no overwatch games, redirecting to overwatch games list')
        return redirect(url_for('overwatch.games_list.games_list'), code=302)
    else:
        try:
            from overtrack_models.orm.overwatch_game_summary import OverwatchGameSummary
            overwatch_game = OverwatchGameSummary.user_id_time_index.get(session.user.user_id, scan_index_forward=False)
        except:
            overwatch_game = None
        try:
            from overtrack_models.orm.apex_game_summary import ApexGameSummary
            apex_game = ApexGameSummary.user_id_time_index.get(session.user.user_id, scan_index_forward=False)
        except:
            apex_game = None
        try:
            from overtrack_models.orm.valorant_game_summary import ValorantGameSummary
            valorant_game = ValorantGameSummary.user_id_timestamp_index.get(session.user.user_id, scan_index_forward=False)
        except:
            valorant_game = None

        logger.info(f'Games: {overwatch_game, apex_game, valorant_game}')

        most_recent = 'overwatch', None
        if overwatch_game:
            most_recent = 'overwatch', overwatch_game.datetime
        if apex_game:
            if not most_recent[1] or apex_game.time > most_recent[1]:
                most_recent = 'apex', apex_game.time
        if valorant_game:
            if not most_recent[1] or valorant_game.datetime > most_recent[1]:
                most_recent = 'valorant', valorant_game.datetime

        logger.info(
            f'Most recent game was {most_recent[0]} at {most_recent[1]}'
        )
        return redirect(url_for(most_recent[0] + '.games_list.games_list'), code=302)


# ------ SIMPLE INFO PAGES  ------
@app.route('/client')
def client():
    return render_template('client.html', meta=WELCOME_META, style_name='overwatch')

@app.route('/welcome')
def welcome():
    return render_template('welcome.html', meta=WELCOME_META, style_name='overwatch')

@app.route('/discord')
def discord_redirect():
    return redirect('https://discord.gg/JywstAB')

@app.route('/faq')
def faq():
    game = request.args.get('game')
    return render_template(
        'faq.html',
        game_name=game if game in ['overwatch', 'apex'] else None
    )


# -------- SITEMAPS + ROBOTS

app.register_blueprint(sitemap_blueprint)

@app.route('/riot.txt')
def riot_proof():
    return '8438891f-f5e7-4ac3-a813-7cb9a7d30ed3'


@app.route('/test', methods=['GET', 'POST'])
def test():
    if 'exception' in request.args:
        return '1/0=' + str(1/0)
    return render_template_string('<pre>{{ form }}</pre><pre>{{ args }}</pre>', form=request.form, args=request.args)
