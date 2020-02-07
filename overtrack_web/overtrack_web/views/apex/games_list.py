import json
import logging
from typing import Optional, Tuple
from urllib.parse import urlparse

import boto3
import requests
import time
from flask import Blueprint, Request, Response, render_template, render_template_string, request, url_for
from itertools import islice
from werkzeug.datastructures import MultiDict

from overtrack_models.dataclasses import typedload
from overtrack_models.dataclasses.apex.apex_game import ApexGame
from overtrack_models.orm.apex_game_summary import ApexGameSummary
from overtrack_models.orm.common import ResultIteratorExt
from overtrack_models.orm.user import User
from overtrack_web.data import ApexRankSummary, ApexSeason, WELCOME_META, apex_data
from overtrack_web.lib import b64_decode, b64_encode
from overtrack_web.lib.authentication import check_authentication, require_login
from overtrack_web.lib.opengraph import Meta
from overtrack_web.lib.session import session
from overtrack_web.views.apex.game import compat_game_data, make_game_description

PAGINATION_SIZE = 30

request: Request = request
logger = logging.getLogger(__name__)
try:
    s3 = boto3.client('s3')
    """ :type s3: boto3_type_annotations.s3.Client """
except:
    logger.exception('Failed to create AWS S3 client - running without admin logs')
    s3 = None

games_list_blueprint = Blueprint('apex.games_list', __name__)


@games_list_blueprint.context_processor
def context_processor():
    return {
        'game_name': 'apex',
    }


@games_list_blueprint.route('')
@require_login
def games_list() -> Response:
    return render_games_list(session.user)


@games_list_blueprint.route('/<string:username>')
def public_games_list(username: str) -> Response:
    try:
        user = User.username_index.get(username.lower())
    except User.DoesNotExist:
        user = None
    if not user or (not user.apex_games_public and not is_superuser()):
        return 'User not found or games not public', 404
    return render_games_list(user, public=True)


@games_list_blueprint.route('/games_pagination')
def games_pagination():
    public = 'username' in request.args
    if public:
        try:
            user = User.username_index.get(request.args['username'].lower())
        except User.DoesNotExist:
            user = None
        if not user or (not user.apex_games_public and not is_superuser()):
            return 'User not found or games not public', 404
    else:
        if check_authentication() is None:
            user = session.user
        else:
            return 'Not logged in', 403
    games_it, is_ranked, season = get_games(user, limit=PAGINATION_SIZE)
    games, next_from = paginate(games_it, username=user.username if public else None)
    return render_template_string(
        '''{% import 'apex/games_list/games_page.html' as games_page with context %}
           {{ games_page.next_page(games, next_from) }}''',
        games=games,
        next_from=next_from,
    )


def is_superuser():
    if check_authentication() is None:
        return session.user.superuser
    else:
        return False


def render_games_list(user: User, public=False, meta_title: Optional[str] = None) -> Response:
    user.refresh()
    games_it, is_ranked, season = get_games(user, limit=PAGINATION_SIZE)
    games, next_from = paginate(games_it, username=user.username if public else None)

    if not len(games):
        logger.info(f'User {user.username} has no games')
        if not public and 'season' not in request.args:
            return render_template('client.html', no_games_alert=True, meta=WELCOME_META)

    # TODO: don't list ranked/unranked if a player has e.g. no ranked games in a season
    seasons = []
    for sid in user.apex_seasons:
        if sid in apex_data.seasons:
            seasons.append(apex_data.seasons[sid])

    logger.info(f'User {user.username} has user.apex_seasons={user.apex_seasons} => {seasons}')
    seasons = sorted(seasons, key=lambda s: s.start, reverse=True)

    t0 = time.time()
    if len(games) and games[0].url:
        try:
            url = urlparse(games[0].url)
            game_object = s3.get_object(
                Bucket=url.netloc.split('.')[0],
                Key=url.path[1:]
            )
            latest_game_data = json.loads(game_object['Body'].read())
        except:
            logger.exception('Failed to fetch game data from S3 - trying HTTP')
            r = requests.get(games[0].url)
            r.raise_for_status()
            latest_game_data = r.json()
        latest_game_data = compat_game_data(latest_game_data)
        latest_game = typedload.load(latest_game_data, ApexGame)
    else:
        latest_game = None
    t1 = time.perf_counter()
    logger.info(f'latest game fetch: {(t1 - t0) * 1000:.2f}ms')

    is_rank_valid = (
        is_ranked and
        latest_game and
        latest_game.rank and
        latest_game.rank.rp is not None and
        latest_game.rank.rp_change is not None
    )
    if is_rank_valid:
        rp = latest_game.rank.rp + latest_game.rank.rp_change
        derived_rank = None
        derived_tier = None
        for rank, (lower, upper) in apex_data.rank_rp.items():
            if lower <= rp < upper:
                derived_rank = rank
                rank_floor, rank_ceil = apex_data.get_tier_window(rp, lower, (upper - lower) // 4)
                if rank != 'apex_predator':
                    division = (upper - lower) // 4
                    tier_ind = (rp - lower) // division
                    derived_tier = ['IV', 'III', 'II', 'I'][tier_ind]
                else:
                    derived_rank = 'apex predator'
                    derived_tier = ''
                    rank_floor = 1000
                    rank_ceil = rp
                break
        rank_summary = ApexRankSummary(rp, rank_floor, rank_ceil, derived_rank, derived_tier)
    else:
        rank_summary = None

    if is_ranked and len(games):
        rp_data = [game.rank.rp for game in reversed(games) if game.rank and game.rank.rp]
        if games[0].rank and games[0].rank.rp is not None and games[0].rank.rp_change is not None:
            rp_data.append(games[0].rank.rp + games[0].rank.rp_change)
    else:
        rp_data = None

    if public and latest_game:
        # description = f'{len(games)} Season {season.index} games\n'
        description = ''
        if rank_summary:
            description += 'Rank: ' + rank_summary.rank.title()
            if rank_summary.tier:
                description += ' ' + rank_summary.tier
            description += '\n'
        description += f'Last game: {make_game_description(games[0], divider=" / ", include_knockdowns=False)}'
        summary_meta = Meta(
            title=(meta_title or user.username) + "'s Games",
            description=description,
            colour=rank_summary.color if rank_summary else '#992e26',
            image_url=url_for('static', filename=f'images/apex/{games[0].rank.rank}.png') if games[0].rank else None
        )
    else:
        summary_meta = WELCOME_META

    return render_template(
        'apex/games_list/games_list.html',
        title=f"Apex Legends | {user.username}'s Games" if public else "My Games",

        games=games,
        next_from=next_from,
        meta=summary_meta,

        season=season,
        seasons=seasons,

        is_ranked=is_ranked,
        rank_summary=rank_summary,
        rp_data=rp_data,

        latest_game=latest_game,

        show_sub_request=not public and not session.user.subscription_active,
    )


def get_games(user: User, limit: Optional[int] = None) -> Tuple[ResultIteratorExt[ApexGameSummary], bool, ApexSeason]:
    try:
        season_id = int(request.args['season'])
        is_ranked = request.args['ranked'].lower() == 'true'
    except:
        season_id = user.apex_last_season
        is_ranked = user.apex_last_game_ranked

    if season_id is None:
        season_id = apex_data.current_season.index
    logger.info(f'Getting games for {user.username} => season_id={season_id}')

    season = apex_data.seasons[season_id]
    range_key_condition = ApexGameSummary.timestamp.between(season.start, season.end)
    filter_condition = ApexGameSummary.season == season_id
    if is_ranked:
        filter_condition &= ApexGameSummary.rank.exists()
    else:
        filter_condition &= ApexGameSummary.rank.does_not_exist()

    if 'last_evaluated' in request.args:
        last_evaluated = json.loads(b64_decode(request.args['last_evaluated']))
    else:
        last_evaluated = None

    t0 = time.perf_counter()
    logger.info(
        f'Getting games for {user.username}: {user.user_id}, {range_key_condition}, {filter_condition} '
        f'with last_evaluated={last_evaluated} and limit={limit}'
    )
    games = ApexGameSummary.user_id_time_index.query(
        user.user_id,
        range_key_condition,
        filter_condition,
        last_evaluated_key=last_evaluated,
        newest_first=True,
        limit=limit,
    )
    t1 = time.perf_counter()
    logger.info(f'Games query: {(t1 - t0) * 1000:.2f}ms')

    return games, is_ranked, season


def paginate(games_it: ResultIteratorExt[ApexGameSummary], username: Optional[str] = None, page_size: int = PAGINATION_SIZE):
    games = list(islice(games_it, page_size))
    if games_it.last_evaluated_key:
        next_args = MultiDict(request.args)
        next_args['last_evaluated'] = b64_encode(json.dumps(games_it.last_evaluated_key))
        if username:
            next_args['username'] = username
        next_from = url_for('apex.games_list.games_pagination', **next_args)
    else:
        next_from = None
    return games, next_from
