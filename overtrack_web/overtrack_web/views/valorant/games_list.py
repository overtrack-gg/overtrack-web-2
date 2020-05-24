import datetime
import json
import logging
import random
from collections import defaultdict
from typing import List, Optional, Tuple, Dict, Any, DefaultDict

import boto3
import time
from dataclasses import dataclass
from flask import Blueprint, Request, render_template, request, url_for
from overtrack_models.dataclasses import s2ts
from overtrack_models.orm.user import User
from overtrack_models.orm.valorant_game_summary import ValorantGameSummary

from overtrack_web.data import WELCOME_META
from overtrack_web.lib import b64_decode, b64_encode, FlaskResponse, parse_args
from overtrack_web.lib.authentication import check_authentication, require_login
from overtrack_web.lib.session import session

PAGINATION_PAGE_MINIMUM_SIZE = 40
PAGINATION_SESSIONS_COUNT_AS = 2
SESSION_MAX_TIME_BETWEEN_GAMES = 2 * 60


request: Request = request
logger = logging.getLogger(__name__)
try:
    s3 = boto3.client('s3')
    """ :type s3: boto3_type_annotations.s3.Client """
except:
    logger.exception('Failed to create AWS S3 client - running without admin logs')
    s3 = None

games_list_blueprint = Blueprint('valorant.games_list', __name__)


@dataclass
class Session:
    games: List[ValorantGameSummary]

    def __init__(self, first_game: ValorantGameSummary):
        self.games = [first_game]
        self.roles: DefaultDict[str, List[ValorantGameSummary]] = defaultdict(list)

    def add_game(self, game: ValorantGameSummary) -> bool:
        """
        Check's if a game should be included in this session, and if so adds it.
        Note that games should be added newest-to-oldest
        :return: If the game was added
        """
        if self.start < game.timestamp:
            raise ValueError(f'Cannot add a game to the middle/beginning of a session')
        elif self.start - (game.timestamp + game.duration) > SESSION_MAX_TIME_BETWEEN_GAMES * 60:
            return False
        else:
            self.games.append(game)
            return True

    @property
    def start(self) -> float:
        return self.games[-1].timestamp

    @property
    def end(self) -> float:
        return self.games[0].timestamp + self.games[0].duration

    def __str__(self) -> str:
        return (
            f'Session('
            f'start={datetime.datetime.fromtimestamp(self.start)}, '
            f'end={datetime.datetime.fromtimestamp(self.end)}, '
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
    return render_games_list(user, public=True, username=username)


@games_list_blueprint.route('/next')
def games_next() -> FlaskResponse:
    next_args = {}
    share_settings = None
    if 'username' in request.args:
        username = request.args['username']
        next_args['username'] = username
        user = resolve_public_user(username)
        if not user:
            return 'Share link not found', 404
    else:
        if check_authentication() is None:
            user = session.user
        else:
            return 'Not logged in', 403

    sessions, last_evaluated = get_sessions(user)

    if last_evaluated:
        next_args['last_evaluated'] = last_evaluated
        next_from = url_for('valorant.games_list.games_next', **next_args)
    else:
        next_from = None

    return render_template(
        'valorant/games_list/sessions_page.html',
        sessions=sessions,
        next_from=next_from,
    )


@games_list_blueprint.context_processor
def context_processor() -> Dict[str, Any]:
    return {
        'game_name': 'valorant',

        # 'sr_change': sr_change,
        # 'rank': rank,
        'random': random,
    }


@games_list_blueprint.app_template_filter('val_result')
def result_filter(won: Optional[bool]) -> str:
    if won is None:
        return '-'
    elif won:
        return 'VICTORY'
    else:
        return 'DEFEAT'


@games_list_blueprint.app_template_filter('val_score')
def score_filter(score: Optional[Tuple[int, int]]) -> str:
    if not score:
        return '? - ?'
    else:
        return f'{score[0]} - {score[1]}'


def resolve_public_user(username: str) -> Optional[User]:
    try:
        user = User.username_index.get(username)  # TODO: make all usernames lower
    except User.DoesNotExist:
        return None
    else:
        if check_superuser():
            logger.info(f'Ignoring valorant_games_public for superuser')
            return user
        elif user.valorant_games_public:
            return user
        else:
            return None


def check_superuser() -> bool:
    if check_authentication() is None:
        return session.user.superuser
    else:
        return False


def render_games_list(user: User, public: bool = False, **next_args: str) -> FlaskResponse:
    user.refresh()

    if not user.valorant_games:
        logger.info(f'User {user.username} has no games')
        if not public:
            return render_template('client.html', no_games_alert=True, meta=WELCOME_META)

    sessions, last_evaluated = get_sessions(user)
    if last_evaluated:
        next_args['last_evaluated'] = last_evaluated
        next_from = url_for('valorant.games_list.games_next', **next_args)
    else:
        next_from = None

    return render_template(
        'valorant/games_list/games_list.html',
        title=user.username.title() + "'s Valorant Games",

        sessions=sessions,
        next_from=next_from,

        show_share_links_edit=not public,
    )


def get_sessions(
    user: User,
    page_minimum_size: int = PAGINATION_PAGE_MINIMUM_SIZE,
    sessions_count_as: int = PAGINATION_SESSIONS_COUNT_AS,
) -> Tuple[List[Session], Optional[str]]:
    logger.info(f'Fetching games for user={user.user_id}: {user.username!r}')

    # merge actual args with parent page args from intercooler (for when this is a pagination fetch)
    logger.info(f'Request args={request.args}')
    args = parse_args(request.args.get('ic-current-url'))
    logger.info(f'Intercooler args={args}')
    args.update(request.args)
    logger.info(f'Merged args={args}')

    # Construct the filter condition combining season, share accounts, show quickplay
    # filter_condition = ValorantGameSummary.season_mode_id == 0
    filter_condition = None
    range_key_condition = None

    # Use last_evaluated from args
    if 'last_evaluated' in args:
        last_evaluated = json.loads(b64_decode(request.args['last_evaluated']))
        logger.info(f'Using last_evaluated={last_evaluated}')
    else:
        last_evaluated = None
        logger.info(f'Using last_evaluated={last_evaluated}')

    # Use a page size that is slightly larger than the minimum number of elements we want, to avoid having to use 2 pages
    page_size = page_minimum_size + 15

    logger.info(
        f'Getting games for user_id={user.user_id}, range_key_condition={range_key_condition}, filter_condition={filter_condition}, '
        f'last_evaluated={last_evaluated}, page_size={page_size}'
    )
    t0 = time.perf_counter()
    sessions: List[Session] = []
    total_games = 0
    last_evaluated_key = None
    query = ValorantGameSummary.user_id_timestamp_index.query(
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
            logger.debug(
                f'    '
                f'Added game to last session, '
                f'offset={s2ts(sessions[-1].games[-2].timestamp - (game.timestamp + game.duration))}, '
                f'game={game}'
            )
        elif total_games + len(sessions) * sessions_count_as <= page_minimum_size:
            sessions.append(Session(game))
            total_games += 1
            logger.debug(f'Added new session {sessions[-1]}, game={game}')
        else:
            logger.info(f'Got {total_games} games over {len(sessions)} sessions - pagination limit reached')
            break
        last_evaluated_key = query.last_evaluated_key
    else:
        last_evaluated_key = None

    t1 = time.perf_counter()
    logger.info(
        f'Building sessions list took {(t1 - t0)*1000:.2f}ms - '
        f'took {total_games / page_size + 0.5:.0f} result pages ({(total_games / page_size)*100:.0f}% of page used)')

    logger.info(f'Got {len(sessions)} sessions:')
    for s in sessions:
        logger.info(f'    {s}')

    if last_evaluated_key is None:
        logger.info(f'Reached end of query - not providing a last_evaluated')
        return sessions, None
    else:
        logger.info(f'Reached end of query with items remaining - returning last_evaluated={last_evaluated_key!r}')
        return sessions, b64_encode(json.dumps(last_evaluated_key))
