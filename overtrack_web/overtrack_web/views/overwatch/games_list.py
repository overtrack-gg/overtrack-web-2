import datetime
import json
import logging
import string
from typing import List, Optional, Tuple, Dict, Any, DefaultDict
from collections import defaultdict
from functools import lru_cache

from itertools import permutations
from urllib.parse import parse_qs, urlparse

import boto3
import time
from dataclasses import dataclass
from flask import Blueprint, Request, render_template, request, url_for, make_response
from werkzeug.datastructures import MultiDict

from overtrack_models.dataclasses import s2ts
from overtrack_models.orm.overwatch_game_summary import OverwatchGameSummary
from overtrack_models.orm.share_link import ShareLink
from overtrack_models.orm.user import User, OverwatchShareSettings
from overtrack_web.data import overwatch_data, WELCOME_META
from overtrack_web.data.overwatch_data import Season
from overtrack_web.lib import b64_decode, b64_encode, FlaskResponse, check_superuser, parse_args, hopeful_int
from overtrack_web.lib.authentication import check_authentication, require_login
from overtrack_web.lib.decorators import restrict_origin
from overtrack_web.lib.session import session
from overtrack_web.views.overwatch import sr_change

PAGINATION_PAGE_MINIMUM_SIZE = 40
PAGINATION_SESSIONS_COUNT_AS = 2
SESSION_MAX_TIME_BETWEEN_GAMES = 45


request: Request = request
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
        self.roles: DefaultDict[str, List[OverwatchGameSummary]] = defaultdict(list)
        self.roles[first_game.role].append(first_game)

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
            self.roles[game.role].append(game)
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

    def start_sr(self, role: str) -> int:
        return self.roles[role][-1].start_sr

    def end_sr(self, role: str) -> int:
        return self.roles[role][0].end_sr

    def start_rank(self, role: str) -> str:
        return self.roles[role][-1].rank

    def end_rank(self, role: str) -> str:
        return self.roles[role][0].rank

    def sr_change(self, role: str) -> str:
        first_game = self.roles[role][-1]
        last_game = self.roles[role][0]
        if first_game.rank == 'placement':
            return '-'
        elif first_game.start_sr and last_game.end_sr:
            if first_game.start_sr == last_game.end_sr:
                return '0'
            else:
                return f'{last_game.end_sr - first_game.start_sr:+}'
        else:
            return '?'

    def roles_sorted(self) -> List[Tuple[str, List[OverwatchGameSummary]]]:
        return sorted(
            [(r, g) for r, g in self.roles.items() if r],
            key=lambda r: ['tank', 'damage', 'support'].index(r[0])
        )

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
    user, share_settings = resolve_public_user(username)
    if not user:
        return 'User does not exist or games not public', 404
    return render_games_list(user, share_settings=share_settings, username=username)


@games_list_blueprint.route('/share/<string:sharekey>')
def shared_games_list(sharekey: str) -> FlaskResponse:
    user, share_settings = resolve_share_key(sharekey)
    if not user:
        return 'Share link not found', 404
    return render_games_list(user, share_settings=share_settings, sharekey=sharekey)


@games_list_blueprint.route('/next')
def games_next() -> FlaskResponse:
    next_args = {}
    share_settings = None
    if 'username' in request.args:
        username = request.args['username']
        next_args['username'] = username
        user, share_settings = resolve_public_user(username)
        if not user:
            return 'Share link not found', 404
    elif 'sharekey' in request.args:
        sharekey = request.args['sharekey']
        next_args['sharekey'] = request.args['sharekey']
        user, share_settings = resolve_share_key(sharekey)
        if not user:
            return 'Share link not found', 404
    else:
        if check_authentication() is None:
            user = session.user
        else:
            return 'Not logged in', 403

    sessions, season, include_quickplay, last_evaluated = get_sessions(user, share_settings=share_settings)

    if last_evaluated:
        next_args['last_evaluated'] = last_evaluated
        next_from = url_for('overwatch.games_list.games_next', **next_args)
    else:
        next_from = None

    return render_template(
        'overwatch/games_list/sessions_page.html',
        sessions=sessions,
        next_from=next_from,
    )


@games_list_blueprint.route('/share_links', methods=['GET', 'POST'])
@require_login
@restrict_origin(restrict_for=['POST'])
def share_links() -> FlaskResponse:
    if request.method == 'POST':
        logger.info(f'Got new share settings {request.form}')

        new_settings = OverwatchShareSettings(
            enabled=request.form.get('enabled', 'off') == 'on',
            accounts=request.form.getlist('accounts') or None,
            include_quickplay=request.form.get('include_quickplay', 'off') == 'on'
        )
        logger.info(f'Created {new_settings}')
        session.user.refresh()
        session.user.overwatch_games_public = new_settings
        session.user.save()

    account_names = list(session.user.overwatch_games_public.accounts or [])
    for name in get_all_account_names(session.user):
        if name not in account_names:
            account_names.append(name)

    return render_template(
        'overwatch/games_list/share_links.html',

        share_link='https://overtrack.gg/overwatch/games/' + session.user.username,
        share_settings=session.user.overwatch_games_public or OverwatchShareSettings(),
        account_names=account_names,
    )


@games_list_blueprint.route('/edit_game/<path:key>')
@require_login
def edit_game(key: str) -> FlaskResponse:
    try:
        summary = OverwatchGameSummary.get(key)
    except OverwatchGameSummary.DoesNotExist as e:
        return 'Invalid game', 403
    if summary.user_id != session.user_id and not session.superuser:
        return 'Invalid game', 403

    summary.competitive = summary.game_type == 'competitive'
    summary.placement = summary.rank == 'placement'

    return render_template(
        'overwatch/game/edit.html',

        edit_source='games_list',
        game=summary,
    )


@games_list_blueprint.context_processor
def context_processor() -> Dict[str, Any]:
    return {
        'game_name': 'overwatch',

        'sr_change': sr_change,
        'map_thumbnail_style': map_thumbnail_style,
        'rank': rank,
    }


def map_thumbnail_style(map_name: str) -> str:
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
def result(s: str) -> str:
    if s == 'UNKNOWN':
        return 'UNK'
    else:
        return s


@games_list_blueprint.app_template_filter('gamemode')
def gamemode(s: str) -> str:
    if s == 'quickplay':
        return 'Quick Play'
    else:
        return s.title()


def resolve_public_user(username: str) -> Tuple[Optional[User], Optional[OverwatchShareSettings]]:
    try:
        user = User.username_index.get(username)  # TODO: make all usernames lower
    except User.DoesNotExist:
        return None, None
    else:
        if check_superuser():
            logger.info(f'Overriding OverwatchShareSettings for superuser')
            return user, OverwatchShareSettings(enabled=True)
        elif user.overwatch_games_public and user.overwatch_games_public.enabled:
            return user, user.overwatch_games_public
        else:
            return None, None


def resolve_share_key(sharekey: str) -> Tuple[Optional[User], Optional[OverwatchShareSettings]]:
    try:
        share_link = ShareLink.get(sharekey)
    except ShareLink.DoesNotExist:
        return None, None
    try:
        user = User.user_id_index.get(share_link.user_id)
    except User.DoesNotExist:
        return None, None
    share_settings = OverwatchShareSettings(
        enabled=True,
        accounts=share_link.player_name_filter,
        include_quickplay=share_link.player_name_filter is None,
    )
    logger.info(f'Generating {share_settings} from {share_link}')
    return user, share_settings


def render_games_list(user: User, share_settings: Optional[OverwatchShareSettings] = None, **next_args: str) -> FlaskResponse:
    user.refresh()

    if not user.overwatch_games:
        logger.info(f'User {user.username} has no games')
        if not share_settings:
            return render_template('client.html', no_games_alert=True, meta=WELCOME_META)

    sessions, current_season, include_quickplay, last_evaluated = get_sessions(user, share_settings=share_settings)

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

    now = datetime.datetime.now()
    trial_end_time = datetime.datetime.utcfromtimestamp(user.trial_end_time or time.time() + 7 * 24 * 60 * 60)
    raw_time_left = trial_end_time - now

    if raw_time_left.days > 0:
        trial_time_left = f'{raw_time_left.days} days'
    elif raw_time_left.seconds > 60 * 60:
        trial_time_left = f'{raw_time_left.seconds // (60 * 60)} hours'
    elif raw_time_left.seconds > 60:
        trial_time_left = f'{raw_time_left.seconds // 60} minutes'
    elif raw_time_left.total_seconds() > 0:
        trial_time_left = f'{raw_time_left.seconds} seconds'
    else:
        trial_time_left = '0 days'

    response = make_response(
        render_template(
            'overwatch/games_list/games_list.html',
            title=user.username + "'s Overwatch Games",

            sessions=sessions,
            next_from=next_from,

            seasons=seasons,
            current_season=current_season,
            show_sub_request=(
                not user.subscription_active and
                not user.free and
                not user.trial_valid and
                share_settings is None
            ),
            show_trial_reminder=(
                not user.account_valid and
                not user.free and
                user.trial_valid and
                share_settings is None
            ),
            trial_time_left=trial_time_left,
            trial_games_left=user.trial_games_remaining,

            allow_toggle_quickplay=not share_settings or share_settings.include_quickplay,
            include_quickplay=include_quickplay,

            show_share_links_edit=share_settings is None,
            show_edit_button=share_settings is None or user.superuser,
        )
    )
    if not share_settings or share_settings.include_quickplay:
        logger.info(f'Setting cookie include_quickplay={include_quickplay}')
        response.set_cookie('include_quickplay', str(int(include_quickplay)))
    return response


def get_sessions(
    user: User,
    share_settings: Optional[OverwatchShareSettings] = None,
    page_minimum_size: int = PAGINATION_PAGE_MINIMUM_SIZE,
    sessions_count_as: int = PAGINATION_SESSIONS_COUNT_AS,
) -> Tuple[List[Session], Optional[Season], bool, Optional[str]]:
    logger.info(f'Fetching games for user={user.user_id}: {user.username!r}')

    # merge actual args with parent page args from intercooler (for when this is a pagination fetch)
    logger.info(f'Request args={request.args}')
    args = parse_args(request.args.get('ic-current-url'))
    logger.info(f'Intercooler args={args}')
    args.update(request.args)
    logger.info(f'Merged args={args}')

    logger.info(f'Share settings={share_settings}')

    # Use season as {specified season, user's last season, current season} in that order
    # Note: when getting sessions for a share link, where the user has played in a new season, but has no visible games will generage an
    # empty page with no way of the viewer knowing which seasons have games. This could be detected, and we could compute the valid seasons
    # for a share link, but...
    if hopeful_int(args.get('season')) in user.overwatch_seasons:
        season = overwatch_data.seasons[int(args['season'])]
        logger.info(f'Using season={season.index} from args')
    elif user.overwatch_last_season in overwatch_data.seasons:
        season = overwatch_data.seasons[user.overwatch_last_season]
        logger.info(f'Using season={season.index} from user.overwatch_last_season')
    else:
        season = overwatch_data.current_season
        logger.info(f'Using season={season.index} from current_season')

    # Use include_quickplay from {share settings, specified season, cookie} in that order, defaulting to True if not set in any
    if share_settings and not share_settings.include_quickplay:
        logger.info(f'Using include_quickplay=False from share settings')
        include_quickplay = False
    elif hopeful_int(args.get('quickplay')) in [0, 1]:
        include_quickplay = bool(int(args['quickplay']))
        logger.info(f'Using include_quickplay={include_quickplay} from request')
    else:
        include_quickplay = int(request.cookies.get('include_quickplay', 1))
        logger.info(f'Using include_quickplay={include_quickplay} from cookie')

    # Use a range key filter for the season
    logger.info(f'Using season time range {datetime.datetime.fromtimestamp(season.start)} -> {datetime.datetime.fromtimestamp(season.end)}')
    range_key_condition = OverwatchGameSummary.time.between(season.start, season.end)

    # Construct the filter condition combining season, share accounts, show quickplay
    filter_condition = OverwatchGameSummary.season == season.index
    if share_settings and share_settings.accounts:
        logger.info(f'Share settings has whitelisted accounts {share_settings.accounts}')
        filter_condition &= OverwatchGameSummary.player_name.is_in(*share_settings.accounts)
    if not include_quickplay:
        filter_condition &= (OverwatchGameSummary.game_type == 'competitive') | OverwatchGameSummary.game_type.does_not_exist()
    else:
        filter_condition &= OverwatchGameSummary.game_type.is_in('quickplay', 'competitive') | OverwatchGameSummary.game_type.does_not_exist()

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
            logger.debug(
                f'    '
                f'Added game to last session, '
                f'offset={s2ts(sessions[-1].games[-2].time - (game.time + game.duration))}, '
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
        return sessions, season, include_quickplay, None
    else:
        logger.info(f'Reached end of query with items remaining - returning last_evaluated={last_evaluated_key!r}')
        return sessions, season, include_quickplay, b64_encode(json.dumps(last_evaluated_key))


def get_all_account_names(user: User, minimum_games=5, _cache={}) -> List[str]:
    try:
        latest_game = OverwatchGameSummary.user_id_time_index.get(
            user.user_id,
            scan_index_forward=False,
        )
    except OverwatchGameSummary.DoesNotExist:
        return []

    # if the first game is the same as the last time we checked, then no new accounts could have been added
    if _cache.get(user.user_id, (None, None))[0] == latest_game.key:
        logger.info(f'Got accounts from cache where user={user.user_id}, latest_game={latest_game.key!r}')
        return _cache[user.user_id][1]

    # Automatically include the latest game for new users
    account_names_with_minimum_games = [latest_game.player_name]
    account_names = []
    for _ in range(64):
        filter_condition = (OverwatchGameSummary.player_name > account_names[-1]) if account_names else None
        query = OverwatchGameSummary.user_id_player_name_index.query(
            user.user_id,
            filter_condition,
            scan_index_forward=True,
            page_size=minimum_games + 1,
            limit=minimum_games + 1,
        )
        logger.info(f'    Checking for games with filter_condition={filter_condition}')

        new_account = None
        count = 0
        for game_with_new_account in query:
            if not new_account:
                new_account = game_with_new_account.player_name
            elif game_with_new_account.player_name != new_account:
                # this query found 2 accounts - stop counting here, and don't add this account so we can count it next
                break
            count += 1
        if new_account:
            if count >= minimum_games:
                logger.info(f'    Got account {new_account!r} with {count} games')
                if new_account not in account_names_with_minimum_games:
                    account_names_with_minimum_games.append(new_account)
            else:
                logger.info(f'    Ignoring account {new_account!r} with {count} games')
            account_names.append(new_account)
        else:
            logger.info(f'Reached end of games')
            break
    else:
        logger.error(f'Stopping account name search early - limit reached')

    logger.info(f'Caching account names for  user={user.user_id}, latest_game={latest_game.key!r}')
    _cache[user.user_id] = (latest_game.key, account_names_with_minimum_games)

    return account_names_with_minimum_games
