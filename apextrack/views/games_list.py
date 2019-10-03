import json
import logging
from urllib.parse import urlparse

import boto3
import time
from typing import Tuple, List, Optional

from flask import Blueprint, Response, request, Request, render_template, url_for

from apextrack.data import WELCOME_META
from apextrack.data.apex import Season, SEASONS, RANK_RP, get_tier_window, RankSummary
from apextrack.lib.authentication import require_login, check_authentication
from apextrack.lib.opengraph import Meta
from apextrack.lib.session import session
from apextrack.views.game import make_game_description
from overtrack_models.apex_game_summary import ApexGameSummary
from overtrack_models.user import User

request: Request = request
logger = logging.getLogger(__name__)
s3 = boto3.client('s3')
games_list_blueprint = Blueprint('games_list', __name__)


@games_list_blueprint.route('/games')
@require_login
def games_list() -> Response:
    return render_games_list(session.user)


def render_games_list(user: User, make_meta: bool = False, meta_title: Optional[str] = None) -> Response:
    games, is_ranked, season = get_games(user)

    if not len(games):
        logger.info(f'User {user.username} has no games')
        return render_template('client.html', no_games_alert=True, meta=WELCOME_META)

    seasons = []
    for sid in user.apex_seasons:
        s = SEASONS[sid]
        seasons.append(s)

    logger.info(f'User {user.username} has user.apex_seasons={user.apex_seasons} => {seasons}')
    seasons = sorted(seasons, key=lambda s: s.start, reverse=True)

    t0 = time.time()
    if len(games) and games[0].url:
        url = urlparse(games[0].url)
        game_object = s3.get_object(
            Bucket=url.netloc.split('.')[0],
            Key=url.path[1:]
        )
        latest_game_data = json.loads(game_object['Body'].read())
    else:
        latest_game_data = None
    t1 = time.perf_counter()
    logger.info(f'latest game fetch: {(t1 - t0) * 1000:.2f}ms')

    is_rank_valid = (
            is_ranked and
            latest_game_data and
            latest_game_data['rank'] and
            latest_game_data['rank']['rp'] is not None and
            latest_game_data['rank']['rp_change'] is not None
    )
    if is_rank_valid:
        rp = latest_game_data['rank']['rp'] + latest_game_data['rank']['rp_change']
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

    if make_meta and latest_game_data:
        description = f'{len(games)} Season {season.index} games\n'
        if rank_summary:
            description += 'Rank: ' + rank_summary.rank.title()
            if rank_summary.tier:
                description += ' ' + rank_summary.tier
            description += '\n'
        description += f'Last game: {make_game_description(games[0], divider=" / ", include_knockdowns=False)}'
        summary_meta = Meta(
            title=(meta_title or latest_game_data['squad']['player']['name']) + "'s Games",
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
        meta=summary_meta,

        season=season,
        seasons=seasons,

        is_ranked=is_ranked,
        rank_summary=rank_summary,
        rp_data=rp_data,

        latest_game=latest_game_data,

        show_sub_request=show_sub_request,
    )


def get_games(user: User) -> Tuple[List[ApexGameSummary], bool, Season]:
    try:
        season_id = int(request.args['season'])
        is_ranked = request.args['ranked'].lower() == 'true'
    except:
        season_id = user.apex_last_season
        is_ranked = user.apex_last_game_ranked

    logger.info(f'Getting games for {user.username} => season_id={season_id}')
    if season_id is None:
        season_id = 2

    season = SEASONS[season_id]
    range_key_condition = ApexGameSummary.timestamp.between(season.start, season.end)
    filter_condition = ApexGameSummary.season == season_id
    if is_ranked:
        filter_condition &= ApexGameSummary.rank.exists()
    else:
        filter_condition &= ApexGameSummary.rank.does_not_exist()

    t0 = time.perf_counter()
    logger.info(f'Getting games for {user.username}: {user.user_id}, {range_key_condition}, {filter_condition}')
    games = list(ApexGameSummary.user_id_time_index.query(user.user_id, range_key_condition, filter_condition, newest_first=True))
    t1 = time.perf_counter()
    logger.info(f'Games query: {(t1 - t0) * 1000:.2f}ms')

    return games, is_ranked, season
