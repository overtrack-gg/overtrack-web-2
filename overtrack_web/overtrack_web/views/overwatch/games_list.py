import datetime
import json
import logging
import string
from typing import List, Optional, Tuple, Union
from urllib.parse import parse_qs, urlparse

import boto3
import time
from dataclasses import dataclass
from flask import Blueprint, Request, Response, render_template, request, url_for
from functools import lru_cache
from werkzeug.datastructures import MultiDict

from overtrack_models.dataclasses import s2ts
from overtrack_models.orm.overwatch_game_summary import OverwatchGameSummary
from overtrack_models.orm.share_link import ShareLink
from overtrack_models.orm.user import User
from overtrack_web.data import overwatch_data
from overtrack_web.data.overwatch_data import Season
from overtrack_web.lib import b64_decode, b64_encode
from overtrack_web.lib.authentication import check_authentication, require_login
from overtrack_web.lib.session import session
from overtrack_web.views.overwatch import OLDEST_SUPPORTED_GAME_VERSION, sr_change

PAGINATION_PAGE_MINIMUM_SIZE = 40
PAGINATION_SESSIONS_COUNT_AS = 2
SESSION_MAX_TIME_BETWEEN_GAMES = 45


request: Request = request
FlaskResponse = Union[Response, Tuple[str, int]]
logger = logging.getLogger(__name__)
try:
    s3 = boto3.client('s3')
    """ :type s3: boto3_type_annotations.s3.Client """
except:
    logger.exception('Failed to create AWS S3 client - running without admin logs')
    s3 = None

games_list_blueprint = Blueprint('overwatch.games_list', __name__)


@dataclass
class Session:
    games: List[OverwatchGameSummary]

    def __init__(self, first_game: OverwatchGameSummary):
        self.games = [first_game]

    def add_game(self, game: OverwatchGameSummary) -> bool:
        """
        Check's if a game should be included in this session, and if so adds it.
        Note that games should be added newest-to-oldest
        :return: If the game was added
        """
        if self.start < game.time:
            raise ValueError(f'Cannot add a game to the middle/beginning of a session')
        elif self.account != game.player_name:
            return False
        elif self.game_mode != game.game_type:
            return False
        elif self.start - (game.time + game.duration) > SESSION_MAX_TIME_BETWEEN_GAMES * 60:
            return False
        else:
            self.games.append(game)
            return True

    @property
    def start(self) -> float:
        return self.games[-1].time

    @property
    def end(self) -> float:
        return self.games[0].time + self.games[0].duration

    @property
    def game_mode(self) -> str:
        return self.games[0].game_type

    @property
    def quickplay(self) -> bool:
        return self.game_mode == 'quickplay'

    @property
    def account(self):
        return self.games[0].player_name

    def __str__(self) -> str:
        return (
            f'Session('
            f'start={datetime.datetime.fromtimestamp(self.start)}, '
            f'end={datetime.datetime.fromtimestamp(self.end)}, '
            f'account={self.account!r}, '
            f'game_mode={self.game_mode}, '
            f'games={len(self.games)}'
            f')'
        )


@games_list_blueprint.route('')
@require_login
def games_list() -> FlaskResponse:
    return render_games_list(session.user)


@games_list_blueprint.route('/<string:username>')
def public_games_list(username: str) -> FlaskResponse:
    user = resolve_public_user(username)
    if not user:
        return 'User does not exist or games not public', 404
    return render_games_list(user, username=username)


@games_list_blueprint.route('/share/<string:sharekey>')
def shared_games_list(sharekey: str) -> FlaskResponse:
    user, share_link = resolve_share_key(sharekey)
    if not user:
        return 'Share link not found', 404
    return render_games_list(user, share_link=share_link, sharekey=sharekey)


@games_list_blueprint.route('/next')
def games_next() -> FlaskResponse:
    next_args = {}
    share_link = None
    if 'username' in request.args:
        username = request.args['username']
        next_args['username'] = username
        user = resolve_public_user(username)
        if not user:
            return 'Share link not found', 404
    elif 'sharekey' in request.args:
        sharekey = request.args['sharekey']
        next_args['sharekey'] = request.args['sharekey']
        user, share_link = resolve_share_key(sharekey)
        if not user:
            return 'Share link not found', 404
    else:
        if check_authentication() is None:
            user = session.user
        else:
            return 'Not logged in', 403

    sessions, season, include_quickplay, last_evaluated = get_sessions(user, share_link=share_link)

    if last_evaluated:
        next_args['last_evaluated'] = last_evaluated
        next_from = url_for('overwatch.games_list.games_next', **next_args)
    else:
        next_from = None

    return render_template(
        'overwatch/games_list/sessions_page.html',
        sessions=sessions,
        next_from=next_from,
        OLDEST_SUPPORTED_GAME_VERSION=OLDEST_SUPPORTED_GAME_VERSION,
    )


@games_list_blueprint.context_processor
def context_processor():
    return {
        'game_name': 'overwatch',

        'sr_change': sr_change,
        'map_thumbnail_style': map_thumbnail_style,
        'rank': rank,
    }


def map_thumbnail_style(map_name: str):
    map_name = map_name.lower().replace(' ', '-')
    map_name = ''.join(c for c in map_name if c in (string.digits + string.ascii_letters + '-'))
    return (
        f'background-image: url({url_for("static", filename="images/overwatch/map_thumbnails/" + map_name + ".jpg")}); '
        f'background-color: #222854;'
        f'display: block;'
        f'background-size: cover;'
        f'background-repeat: no-repeat;'
        f'background-position: center;'
    )


def rank(game: OverwatchGameSummary) -> str:
    if game.rank:
        return game.rank
    elif game.end_sr:
        return overwatch_data.sr_to_rank(game.end_sr)
    elif game.start_sr:
        return overwatch_data.sr_to_rank(game.start_sr)
    else:
        return 'unknown'


@games_list_blueprint.app_template_filter('result')
def result(s: str):
    if s == 'UNKNOWN':
        return 'UNK'
    else:
        return s


@games_list_blueprint.app_template_filter('gamemode')
def gamemode(s: str):
    if s == 'quickplay':
        return 'Quick Play'
    else:
        return s.title()


def resolve_public_user(username: str) -> Optional[User]:
    try:
        user = User.username_index.get(username)  # TODO: make all usernames lower
    except User.DoesNotExist:
        return None
    if user.overwatch_games_public:
        return user
    elif check_superuser():
        return user
    return None


def resolve_share_key(sharekey: str) -> Tuple[Optional[User], Optional[ShareLink]]:
    try:
        share_link = ShareLink.get(sharekey)
    except ShareLink.DoesNotExist:
        return None, None
    try:
        user = User.user_id_index.get(share_link.user_id)
    except User.DoesNotExist:
        return None, None
    return user, share_link


def check_superuser() -> bool:
    if check_authentication() is None:
        return session.user.superuser
    else:
        return False


def render_games_list(user: User, share_link: Optional[ShareLink] = None, **next_args: str) -> Response:
    user.refresh()
    sessions, current_season, include_quickplay, last_evaluated = get_sessions(user, share_link=share_link)

    seasons = [
        s for i, s in overwatch_data.seasons.items() if i in user.overwatch_seasons
    ]
    seasons.sort(key=lambda s: s.start, reverse=True)

    if last_evaluated:
        args = dict(next_args)
        args['last_evaluated'] = last_evaluated
        next_from = url_for('overwatch.games_list.games_next', **args)
    else:
        next_from = None

    return render_template(
        'overwatch/games_list/games_list.html',
        sessions=sessions,
        next_from=next_from,

        seasons=seasons,
        current_season=current_season,

        include_quickplay=include_quickplay,

        OLDEST_SUPPORTED_GAME_VERSION=OLDEST_SUPPORTED_GAME_VERSION,
    )


def get_sessions(
    user: User,
    share_link: Optional[ShareLink] = None,
    page_minimum_size: int = PAGINATION_PAGE_MINIMUM_SIZE,
    sessions_count_as: int = PAGINATION_SESSIONS_COUNT_AS,
) -> Tuple[List[Session], Optional[Season], bool, Optional[str]]:

    if hopeful_int(request.args.get('season')) in user.overwatch_seasons:
        # called from /games - parse season from ?season=N
        logger.info(f'Using season from request args: {request.args}')
        season = overwatch_data.seasons[int(request.args['season'])]
    elif hopeful_int(parse_args(request.args.get('ic-current-url')).get('season')) in user.overwatch_seasons:
        # called from intercooler pagination - parse season from ?ic-current-url='/overtwatch/games?season=N'
        logger.info(f'Using season from ic-current-url args: {parse_args(request.args["ic-current-url"])}')
        season = overwatch_data.seasons[int(parse_args(request.args['ic-current-url'])['season'])]
    elif user.overwatch_last_season:
        logger.info(f'Using season from user.overwatch_last_season: {user.overwatch_last_season}')
        season = overwatch_data.seasons[user.overwatch_last_season]
    else:
        logger.info(f'Using season from current_season')
        season = overwatch_data.current_season

    if 'quickplay' in request.args:
        include_quickplay = bool(int(request.args['quickplay']))
    else:
        # TODO: from cookie (if not share?)
        include_quickplay = True

    logger.info(f'Getting games for {user.username} => season={season}')

    season = overwatch_data.seasons[season.index]
    range_key_condition = OverwatchGameSummary.time.between(season.start, season.end)
    filter_condition = OverwatchGameSummary.season == season.index

    if share_link:
        logger.info(f'Share link {share_link.share_key!r} has whitelisted accounts {share_link.player_name_filter}')
        filter_condition &= OverwatchGameSummary.player_name.is_in(*share_link.player_name_filter)

    logger.info(f'include_quickplay={include_quickplay}')
    if not include_quickplay:
        filter_condition &= OverwatchGameSummary.game_type == 'competitive'
    else:
        filter_condition &= OverwatchGameSummary.game_type.is_in('quickplay', 'competitive')

    if 'last_evaluated' in request.args:
        last_evaluated = json.loads(b64_decode(request.args['last_evaluated']))
    else:
        last_evaluated = None

    # Set the limit past the minimum games by the 95percentile of session lengths.
    # This means we can (usually) load the full session that puts the total game count over
    # minimum_required_games without incurring another fetch
    page_size = page_minimum_size + 20

    logger.info(
        f'Getting games for {user.username}: {user.user_id}, {range_key_condition}, {filter_condition} '
        f'with last_evaluated={last_evaluated} and page_size={page_size}'
    )
    t0 = time.perf_counter()
    sessions: List[Session] = []
    total_games = 0
    last_evaluated_key = None
    query = OverwatchGameSummary.user_id_time_index.query(
        user.user_id,
        range_key_condition,
        filter_condition,
        newest_first=True,
        last_evaluated_key=last_evaluated,
        page_size=page_size,
    )
    for game in query:
        if sessions and sessions[-1].add_game(game):
            total_games += 1
            logger.info(
                f'    '
                f'Added game to last session, '
                f'offset={s2ts(sessions[-1].games[-2].time - (game.time + game.duration))}, '
                f'game={game}'
            )
        elif total_games + len(sessions) * sessions_count_as <= page_minimum_size:
            sessions.append(Session(game))
            total_games += 1
            logger.info(f'Added new session {sessions[-1]}, game={game}')
        else:
            logger.info(f'Got {total_games} games over {len(sessions)} sessions - pagination limit reached')
            break
        last_evaluated_key = query.last_evaluated_key
    else:
        last_evaluated_key = None

    t1 = time.perf_counter()
    logger.info(f'Building sessions list took {(t1 - t0)*1000:.2f}ms - took {total_games / page_size + 0.5:.0f} result pages')

    logger.info(f'Got {len(sessions)} sessions:')
    for s in sessions:
        logger.info(f'    {s}')

    if last_evaluated_key is None:
        logger.info(f'Reached end of query - not providing a last_evaluated')
        return sessions, season, include_quickplay, None
    else:
        logger.info(f'Reached end of query with items remaining - returning last_evaluated={last_evaluated_key!r}')
        return sessions, season, include_quickplay, b64_encode(json.dumps(last_evaluated_key))


def hopeful_int(s: Optional[str]) -> Optional[int]:
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


@lru_cache()
def parse_args(url: Optional[str]) -> MultiDict:
    if not url:
        return MultiDict()
    return MultiDict(parse_qs(urlparse(url).query))
