import datetime
import json
import logging
import time
from typing import Optional, Tuple, NamedTuple
from urllib.parse import urlparse

import boto3
from dataclasses import dataclass
from flask import Flask, Response, render_template, url_for as flask_url_for, request
from flask_bootstrap import Bootstrap

from api.authentication import Authentication, check_authentication, require_authentication
from api.session import session
from blueprints.discord_bot import discord_bot_blueprint
from blueprints.login import login, require_login
from blueprints.stats import results_blueprint
from models.apex_game_summary import ApexGameSummary
from overtrack.util import s2ts

app = Flask(__name__)
bootstrap = Bootstrap(app)

logs = boto3.client('logs')
s3 = boto3.client('s3')

logger = logging.getLogger(__name__)

rank_rp = {
    'bronze': (0, 120),
    'silver': (120, 280),
    'gold': (280, 480),
    'platinum': (480, 720),
    'diamond': (720, 1000),
    'apex_predator': (1000, 10_000)
}

app.register_blueprint(login)
app.register_blueprint(discord_bot_blueprint, url_prefix='/discord_bot')
app.register_blueprint(results_blueprint, url_prefix='/stats')


def url_for(endpoint, **values):
    if endpoint == 'static' and 'filename' in values:
        return 'https://d2igtsro72if25.cloudfront.net/2/' + values['filename']
    else:
        return flask_url_for(endpoint, **values)


if app.config['DEBUG']:
    url_for = app.jinja_env.globals['url_for']
else:
    app.jinja_env.globals['url_for'] = url_for


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


@dataclass
class Season:
    index: int
    start: float
    end: float

    @property
    def name(self) -> str:
        return f'Season {self.index}'


class RankSummary(NamedTuple):
    rp: int
    floor: int
    ceil: int
    rank: str
    tier: str

    @property
    def uri(self) -> str:
        return 'predator' if self.rank == 'apex predator' else self.rank

    @property
    def color(self) -> str:
        return {
            'bronze': '#402D25',
            'silver': '#444448',
            'gold': '#4d4030',
            'platinum': '#24424a',
            'diamond': '#3a4b9e',
            'apex predator': '#8a1f1c'
        }[self.rank]


_PDT = datetime.timezone(datetime.timedelta(hours=-7))
_season_1_start = datetime.datetime.strptime(
    # https://twitter.com/PlayApex/status/1107733497450356742
    'Mar 19 2019 10:00AM',
    '%b %d %Y %I:%M%p'
).replace(tzinfo=_PDT)
_season_2_start = datetime.datetime.strptime(
    'Jul 2 2019 10:00AM',
    '%b %d %Y %I:%M%p'
).replace(tzinfo=_PDT)

SEASONS = [
    Season(0, 0, _season_1_start.timestamp()),
    Season(1, _season_1_start.timestamp(), _season_2_start.timestamp()),
    Season(2, _season_2_start.timestamp(), _season_2_start.timestamp() + 9072000_00)
]


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
    dt = datetime.datetime.fromtimestamp(t)
    date = dt.strftime('%c').split(':', 1)[0].rsplit(' ', 1)[0]
    #return date + ' ' + 
    return dt.strftime('%I:%M %p')


def duration(t: Optional[float]):
    if t is None:
        return '?'
    return s2ts(t).split(':', 1)[1]


def format_rp(v: Optional[int]):
    if v is None:
        return '?'
    elif v == 0:
        return '0'
    else:
        return f'{v:+}'


def get_tier_window(rp: int, tier_entry: int, tier_step: int) -> Tuple[int, int]:
    return (
        ((rp - tier_entry) // tier_step) * tier_step + tier_entry,
        ((rp - tier_entry) // tier_step + 1) * tier_step + tier_entry
    )


base_context = {
    'to_ordinal': to_ordinal,
    's2ts': duration,
    'strftime': strftime,
    'image_url': image_url,
    'champion_colour': champion_colour,
    'format_rp': format_rp
}


@app.route('/client')
def client():
    return render_template('client.html')


@app.route('/welcome')
def welcome():
    return render_template('welcome.html')


def render_games_list(user_id: int) -> Response:
    t0 = time.perf_counter()
    try:
        season_id = int(request.args['season'])
        is_ranked = request.args['ranked'].lower() == 'true'
    except:
        first_game: Optional[ApexGameSummary] = next(ApexGameSummary.user_id_time_index.query(user_id, newest_first=True, limit=1), None)
        if not first_game:
            return render_template('client.html', no_games_alert=True)
        season_id = first_game.season
        is_ranked = first_game.rank is not None

    season = SEASONS[season_id]
    range_key_condition = ApexGameSummary.timestamp.between(season.start, season.end)

    if is_ranked:
        filter_condition = ApexGameSummary.rank.exists()
    else:
        filter_condition = ApexGameSummary.rank.does_not_exist()

    t1 = time.perf_counter()
    games = list(ApexGameSummary.user_id_time_index.query(user_id, range_key_condition, filter_condition, newest_first=True))
    t2 = time.perf_counter()

    if len(games) and games[0].url:
        url = urlparse(games[0].url)
        game_object = s3.get_object(
            Bucket=url.netloc.split('.')[0],
            Key=url.path[1:]
        )
        latest_game_data = json.loads(game_object['Body'].read())
    else:
        latest_game_data = None
    t3 = time.perf_counter()

    is_rank_valid = (
        is_ranked and
        latest_game_data and
        latest_game_data['rank'] and
        latest_game_data['rank']['rank'] is not None and
        latest_game_data['rank']['rank_tier'] is not None and
        latest_game_data['rank']['rp'] is not None and
        latest_game_data['rank']['rp_change'] is not None
    )
    if is_rank_valid:
        rp = latest_game_data['rank']['rp'] + latest_game_data['rank']['rp_change']
        derived_rank = None
        derived_tier = None
        for rank, (lower, upper) in rank_rp.items():
            if lower <= rp < upper:
                derived_rank = rank
                floor, ceil = get_tier_window(rp, lower, (upper - lower) // 4)
                if rank != 'apex_predator':
                    division = (upper - lower) // 4
                    tier_ind = (rp - lower) // division
                    derived_tier = ['IV', 'III', 'II', 'I'][tier_ind]
                else:
                    derived_rank = 'apex predator'
                    derived_tier = ''
                break
        else:
            floor = 1000
            ceil = rp
        rank_summary = RankSummary(rp, floor, ceil, derived_rank, derived_tier)
    else:
        rank_summary = None

    logger.info(f'Season selection: {(t1 - t0)*1000:.2f}ms, games query: {(t2 - t1)*1000:.2f}ms, latest game fetch: {(t3 - t2)*1000:.2f}ms')

    if is_ranked and len(games):
        rp_data = [game.rank.rp for game in reversed(games) if game.rank and game.rank.rp]
        print([game.rank for game in reversed(games)])
        if games[0].rank and games[0].rank.rp_change is not None:
            rp_data.append(games[0].rank.rp + games[0].rank.rp_change)
    else:
        rp_data = None

    return render_template(
        'games/games.html',
        games=games,

        season=season,
        seasons=[2, 1],

        is_ranked=is_ranked,
        rank_summary=rank_summary,
        rp_data=rp_data,

        latest_game=latest_game_data,
        **base_context
    )

@app.route('/')
def root():
    if check_authentication() is None:
        return render_games_list(session.user_id)
    else:
        return render_template('welcome.html')


@app.route('/games')
@require_login
def games_list():
    return render_games_list(session.user_id)


@app.route('/game/<path:key>')
def game(key: str):
    summary = ApexGameSummary.get(key)
    logger.info(f'Fetching {summary.url}')

    url = urlparse(summary.url)
    game_object = s3.get_object(
        Bucket=url.netloc.split('.')[0],
        Key=url.path[1:]
    )
    game_data = json.loads(game_object['Body'].read())

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

    if check_authentication() is None and session.superuser:
        if 'frames' in game_object['Metadata']:
            frames_url = urlparse(game_object['Metadata']['frames'])
            frames_object = s3.get_object(
                Bucket=frames_url.netloc,
                Key=frames_url.path[1:]
            )
            frames_metadata = frames_object['Metadata']
            if 'log' in frames_metadata:
                del frames_metadata['log']  # already have this
            frames_metadata['_href'] = s3.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': frames_url.netloc,
                    'Key': frames_url.path[1:]
                }
            )

        else:
            frames_metadata = None

        if 'log' in game_object['Metadata'] and 'start' in game_object['Metadata']['log']:
            log_url = urlparse(game_object['Metadata']['log'])
            print(log_url.fragment)
            log_params = dict(e.split('=') for e in log_url.fragment.split(':', 1)[1].split(';'))
            print(log_params)

            log_time = datetime.datetime.strptime(log_params['start'], "%Y-%m-%dT%H:%M:%SZ")
            tz_offset = datetime.datetime.now() - datetime.datetime.utcnow()
            log_data = logs.get_log_events(
                logGroupName=log_params['group'],
                logStreamName=log_params['stream'],
                startTime=int((log_time + tz_offset).timestamp() * 1000)
            )
            log_lines = []
            for i, e in enumerate(log_data['events']):
                log_lines.append(e['message'].strip())
                if i > 10 and 'END RequestId' in e['message']:
                    break
        else:
            log_lines = []

        game_metadata = game_object['Metadata']
        game_metadata['_href'] = summary.url

        admin_data = {
            'game_metadata': game_metadata,
            'frames_metadata': frames_metadata,
            'log': log_lines
        }
    else:
        admin_data = None

    return render_template(
        'game/game.html',
        summary=summary,
        game=game_data,
        is_ranked=summary.rank is not None,

        og_title=og_title,
        theme_colour=theme_color,
        og_description=og_description,

        admin_data=admin_data,

        **base_context
    )


# TODO: support a summary in link previews for games lists


@app.route('/eeveea_')
def eeveea_games():
    return render_games_list(347766573)


@app.route('/mendokusaii')
def mendokusaii_games():
    return render_games_list(-3)


@app.route('/heylauren')
def heylauren_games():
    return render_games_list(-420)


@app.route("/by_key/<string:key>")
@require_authentication(superuser_required=True)
def games_by_key(key: str):
    return render_games_list(int(key))


from overtrack.util.logging_config import config_logger
config_logger(__name__, logging.INFO, False)
