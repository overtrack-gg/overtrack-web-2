import base64
import json
import logging
from typing import Optional, Tuple
from urllib.parse import urlparse

import boto3
import requests
import time
from flask import Blueprint, Request, Response, render_template, request, url_for, render_template_string
from itertools import islice
from werkzeug.datastructures import MultiDict

from overtrack_models.dataclasses import typedload
from overtrack_models.dataclasses.apex.apex_game import ApexGame
from overtrack_models.orm.apex_game_summary import ApexGameSummary
from overtrack_models.orm.common import ResultIteratorExt
from overtrack_models.orm.user import User
from overtrack_web.data import WELCOME_META
from overtrack_web.data.apex import RANK_RP, RankSummary, SEASONS, Season, get_tier_window
from overtrack_web.lib.authentication import check_authentication, require_login
from overtrack_web.lib.opengraph import Meta
from overtrack_web.lib.session import session
from overtrack_web.views.apex.game import make_game_description, compat_game_data

PAGINATION_SIZE = 30

request: Request = request
logger = logging.getLogger(__name__)
try:
    s3 = boto3.client('s3')
    """ :type s3: boto3_type_annotations.s3.Client """
except:
    logger.exception('Failed to create AWS S3 client - running without admin logs')
    s3 = None

games_list_blueprint = Blueprint('apex_games_list', __name__)


@games_list_blueprint.route('')
@require_login
def games_list() -> Response:
    return render_games_list(session.user)


def render_games_list(user: User, make_meta: bool = False, meta_title: Optional[str] = None) -> Response:
    user.refresh()
    games_it, is_ranked, season = get_games(user, limit=PAGINATION_SIZE)
    games, next_from = paginate(games_it, PAGINATION_SIZE)

    if not len(games):
        logger.info(f'User {user.username} has no games')
        return render_template('client.html', no_games_alert=True, meta=WELCOME_META)

    seasons = []
    for sid in user.apex_seasons:
        if sid in SEASONS:
            s = SEASONS[sid]
            seasons.append(s)

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
        for rank, (lower, upper) in RANK_RP.items():
            if lower <= rp < upper:
                derived_rank = rank
                rank_floor, rank_ceil = get_tier_window(rp, lower, (upper - lower) // 4)
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
        rank_summary = RankSummary(rp, rank_floor, rank_ceil, derived_rank, derived_tier)
    else:
        rank_summary = None

    if is_ranked and len(games):
        rp_data = [game.rank.rp for game in reversed(games) if game.rank and game.rank.rp]
        if games[0].rank and games[0].rank.rp is not None and games[0].rank.rp_change is not None:
            rp_data.append(games[0].rank.rp + games[0].rank.rp_change)
    else:
        rp_data = None

    if make_meta and latest_game:
        # description = f'{len(games)} Season {season.index} games\n'
        description = ''
        if rank_summary:
            description += 'Rank: ' + rank_summary.rank.title()
            if rank_summary.tier:
                description += ' ' + rank_summary.tier
            description += '\n'
        description += f'Last game: {make_game_description(games[0], divider=" / ", include_knockdowns=False)}'
        summary_meta = Meta(
            title=(meta_title or latest_game.squad.player.name) + "'s Games",
            description=description,
            colour=rank_summary.color if rank_summary else '#992e26',
            image_url=url_for('static', filename=f'images/{games[0].rank.rank}.png') if games[0].rank else None
        )
    else:
        summary_meta = WELCOME_META

    if check_authentication() is None:
        show_sub_request = not session.user.subscription_active
    else:
        show_sub_request = False

    return render_template(
        'games_list/games_list.html',
        games=games,
        next_from=next_from,
        meta=summary_meta,

        season=season,
        seasons=seasons,

        is_ranked=is_ranked,
        rank_summary=rank_summary,
        rp_data=rp_data,

        latest_game=latest_game,

        show_sub_request=show_sub_request,
    )


@games_list_blueprint.route('/games_pagination')
@require_login
def games_pagination():
    games_it, is_ranked, season = get_games(session.user, limit=PAGINATION_SIZE)
    games, next_from = paginate(games_it, PAGINATION_SIZE)
    return render_template_string(
        '''
            {% import 'games_list/games_page.html' as games_page with context %}
            {{ games_page.next_page(games, next_from) }}
        ''',
        games=games,
        next_from=next_from,
    )


def get_games(user: User, limit: Optional[int] = None) -> Tuple[ResultIteratorExt[ApexGameSummary], bool, Season]:
    try:
        season_id = int(request.args['season'])
        is_ranked = request.args['ranked'].lower() == 'true'
    except:
        season_id = user.apex_last_season
        is_ranked = user.apex_last_game_ranked

    if season_id is None:
        season_id = 3
    logger.info(f'Getting games for {user.username} => season_id={season_id}')

    season = SEASONS[season_id]
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


def paginate(games_it: ResultIteratorExt[ApexGameSummary], page_size: int):
    games = list(islice(games_it, page_size))
    if games_it.last_evaluated_key:
        next_args = MultiDict(request.args)
        next_args['last_evaluated'] = b64_encode(json.dumps(games_it.last_evaluated_key))
        next_from = url_for('apex_games_list.games_pagination', **next_args)
    else:
        next_from = None
    return games, next_from


def b64_encode(s: str) -> str:
    encoded = base64.urlsafe_b64encode(s.encode()).decode()
    return encoded.rstrip("=")


def b64_decode(s: str) -> str:
    padding = 4 - (len(s) % 4)
    s = s + ("=" * padding)
    return base64.urlsafe_b64decode(s.encode()).decode()
