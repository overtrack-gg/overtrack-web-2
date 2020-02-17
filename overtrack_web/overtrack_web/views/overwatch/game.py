import os

import collections
import json
import logging
import string
import warnings
from typing import List, Optional, Sequence
from urllib.parse import urlparse

import boto3
import requests
from dataclasses import asdict, fields, is_dataclass
from flask import Blueprint, Request, render_template, request, url_for, render_template_string, Response
from itertools import chain
from overtrack_models.dataclasses.overwatch.basic_types import Map
from overtrack_models.dataclasses.overwatch.overwatch_game import OverwatchGame
from overtrack_models.dataclasses.overwatch.statistics import HeroStats

from overtrack_models.dataclasses.typedload import referenced_typedload
from overtrack_models.orm.overwatch_game_summary import OverwatchGameSummary
from overtrack_web.data import overwatch_data
from overtrack_web.lib.authentication import check_authentication
from overtrack_web.lib.opengraph import Meta
from overtrack_web.lib.session import session
from overtrack_web.views.overwatch import OLDEST_SUPPORTED_GAME_VERSION, sr_change
from overtrack_web.views.overwatch.games_list import map_thumbnail_style

GAMES_BUCKET = 'overtrack-overwatch-games'
COLOURS = {
    'WIN': '#62c462',
    'LOSS': '#ee5f5b',
    'DRAW': '#f89406',
}

request: Request = request
logger = logging.getLogger(__name__)
try:
    s3 = boto3.client('s3')
    """ :type s3: mypy_boto3.s3.Client """
    s3.list_objects_v2(Bucket=GAMES_BUCKET)
except:
    logger.exception('Failed to create AWS S3 client - using HTTP for downloading games')
    s3 = None
try:
    logs = boto3.client('logs')
    """ :type s3: boto3_type_annotations.s3.Client """
except:
    logger.exception('Failed to create AWS logs client - running without admin logs')
    logs = None

game_blueprint = Blueprint('overwatch.game', __name__)


@game_blueprint.route('/<path:key>')
def game(key: str):
    try:
        summary = OverwatchGameSummary.get(key)
    except OverwatchGameSummary.DoesNotExist:
        return 'Game does not exist', 404

    game = load_game(summary)
    game.timestamp = summary.time

    if game.teams.owner and game.result != 'UNKNOWN':
        title = f'{game.teams.owner.name}\'s {game.result} on {game.map.name}'
    elif game.teams.owner:
        title = f'{game.teams.owner.name}\'s game on {game.map.name}'
    else:
        title = f'{key.split("/", 1)[0]}\'s game on {game.map.name}'

    dev_info = get_dev_info(summary, game)

    return render_template(
        'overwatch/game/game.html',

        title=title,
        meta=Meta(
            title=title,
            image_url=url_for('overwatch.game.game_card_png', key=key, _external=True),
            summary_large_image=True,
            colour=COLOURS.get(game.result, 'gray')
        ),

        summary=summary,
        game=game,

        dev_info=dev_info,

        OLDEST_SUPPORTED_GAME_VERSION=OLDEST_SUPPORTED_GAME_VERSION,
    )


@game_blueprint.route('<path:key>/card')
def game_card(key: str):
    try:
        game = OverwatchGameSummary.get(key)
    except OverwatchGameSummary.DoesNotExist:
        return 'Game does not exist', 404

    return render_template_string(
        '''
            <!DOCTYPE html>
            <html lang="en">
                <head>
                    <title>{{ title }}</title>
                    <link rel="stylesheet" type="text/css" href="{{ url_for('static', filename='css/' + game_name + '.css') }}">
                    <style>
                        body {
                            background-color: rgba(0, 0, 0, 0);
                        }
                        .game-summary {
                            margin: 0 !important;
                        }
                    </style>
                </head>
                <body>
                    {% include 'overwatch/games_list/game_card.html' %}
                </body>
            </html>
        ''',
        title='Card',
        game=game,
        OLDEST_SUPPORTED_GAME_VERSION=OLDEST_SUPPORTED_GAME_VERSION,

        map_thumbnail_style=map_thumbnail_style,
    )


@game_blueprint.route('/<path:key>/card.png')
def game_card_png(key: str):
    if 'RENDERTRON_URL' not in os.environ:
        return 'Rendertron url not set on server', 500
    try:
        r = requests.get(
            ''.join((
                os.environ['RENDERTRON_URL'],
                'screenshot/',
                url_for('overwatch.game.game_card', key=key, _external=True),
                '?width=356&height=80'
            )),
            timeout=15,
        )
    except:
        logger.exception('Rendertron failed to respond within the timeout')
        return 'Rendertron failed to respond within the timeout', 500
    try:
        r.raise_for_status()
    except:
        logger.exception('Rendertron encountered an error fetching screenshot')
        return f'Rendertron encountered an error fetching screenshot: got status {r.status_code}', 500

    return Response(
        r.content,
        headers=dict(r.headers)
    )


@game_blueprint.context_processor
def context_processor():
    return {
        'game_name': 'overwatch',

        'sr_change': sr_change,

        'ability_is_ult': ability_is_ult,
        'get_ult_ability': get_ult_ability,

        'sort_stats': sort_stats,
        'get_stat_type': get_stat_type,

        'asdict': asdict,
    }


def ability_is_ult(ability) -> bool:
    if not ability:
        return False
    hero_name, ability_name = ability.split('.')
    hero = overwatch_data.heroes.get(hero_name)

    if ability_name in ['high_noon', 'dragon_blade']:
        # legacy ability names
        return True
    if not hero:
        warnings.warn(f'Could not get hero data for {hero_name}', RuntimeWarning)
        return False
    if not hero.ult:
        warnings.warn(f'Hero {hero_name} does not have ult defined', RuntimeWarning)
        return False
    return ability_name == hero.ult


def get_ult_ability(hero):
    if not hero or hero not in overwatch_data.heroes:
        return None
    return f'{hero}.{overwatch_data.heroes.get(hero).ult}'


def sort_stats(stats: Sequence[HeroStats]) -> List[HeroStats]:
    stats = sorted(list(stats), key=lambda s: (s.hero != 'all heroes', s.hero))
    heroes = [s.hero for s in stats]
    if 'all heroes' in heroes and len(heroes) == 2:
        # only 'all heroes' and one other
        stats = [s for s in stats if s.hero != 'all heroes']
    else:
        stats = [s for s in stats if s.time_played > 60]

    return stats


def get_stat_type(hero_name: str, stat_name: str) -> str:
    if hero_name in overwatch_data.heroes:
        hero = overwatch_data.heroes[hero_name]
        stats_by_name = {
            s.name: s
            for s in chain(*hero.stats)
        }
        if stat_name in stats_by_name:
            stat = stats_by_name[stat_name]
            if stat.stat_type == 'maximum':
                return 'value'
            if stat.stat_type == 'average':
                return 'average'
            elif stat.stat_type == 'best':
                return 'best'
            else:
                logger.error(f"Don't know how to handle stat type {stat.stat_type!r} for {hero_name}: {stat_name!r}")
                return 'value'

    logger.error(f"Couldn't get stat type for {hero_name}: {stat_name!r}")
    return 'value'


@game_blueprint.app_template_filter('map_jumbo_style')
def map_jumbo_style(map_: Map):
    map_name = map_.name.lower().replace(' ', '-')
    map_name = ''.join(c for c in map_name if c in (string.digits + string.ascii_letters + '-'))
    return (
        f'background-image: linear-gradient(#222854 0px, rgba(0, 0, 0, 0.42) 100%), '
        f'url({url_for("static", filename="images/overwatch/map_banners/" + map_name + ".jpg")}); '
        f'background-color: #222854;'
    )


@game_blueprint.app_template_filter('format_number')
def format_number(v: Optional[float], precision: Optional[float] = 1):
    if v is None:
        return v
    if precision is None:
        if v > 500:
            precision = 0
        else:
            precision = 1
    return f'{v:,.{precision}f}'


@game_blueprint.app_template_filter('hero_name')
def hero_name(h: str):
    if h in overwatch_data.heroes:
        return overwatch_data.heroes[h].name
    else:
        return h.title()


def load_game(summary: OverwatchGameSummary) -> OverwatchGame:
    try:
        game_object = s3.get_object(
            Bucket=GAMES_BUCKET,
            Key=summary.key + '.json'
        )
        game_data = json.loads(game_object['Body'].read())
    except:
        game_object = None
        if s3:
            logger.exception('Failed to fetch game data from S3 - trying HTTP')
        r = requests.get(f'https://overtrack-overwatch-games.s3.amazonaws.com/{summary.key}.json')
        r.raise_for_status()
        game_data = r.json()

    return referenced_typedload.load(game_data, OverwatchGame)


def get_dev_info(summary, game):
    if check_authentication() is not None or not session.user.superuser:
        return None

    summary_dict = summary.asdict()
    summary_dict['key'] = (summary.key, f'https://overtrack-overwatch-games.s3.amazonaws.com/{summary.key}.json')
    try:
        frames_url = urlparse(summary.frames_uri)
        # noinspection PyNoneFunctionAssignment
        signed_url = s3.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': frames_url.netloc,
                'Key': frames_url.path[1:]
            }
        )
        summary_dict['frames_uri'] = (summary.frames_uri, signed_url)
    except:
        pass

    def _quickdump(val):
        if isinstance(val, (tuple, str)):
            return val
        elif isinstance(val, collections.Sequence):
            return '...'
        else:
            rep = repr(val)
            if len(rep) < 50:
                return rep
            else:
                return rep[:50 - 3] + '...'

    game_dict = {}
    extras = {}
    for f in fields(game):
        if not is_dataclass(getattr(game, f.name)):
            game_dict[f.name] = getattr(game, f.name)
        else:
            dc = getattr(game, f.name)
            dc_data = []
            extras[f'Game.{f.name}'] = dc_data
            for ff in fields(dc):
                val = getattr(getattr(game, f.name), ff.name)
                if is_dataclass(val):
                    dc_data.append((ff.name, ''))
                    for fff in fields(val):
                        dc_data.append(('\u00a0' * 6 + '.' + fff.name, _quickdump(getattr(val, fff.name))))
                elif isinstance(val, list) and len(val) <= 6:
                    dc_data.append((ff.name, ''))
                    for i, v in enumerate(val):
                        dc_data.append(('\u00a0' * 6 + '.' + str(i), _quickdump(v)))
                else:
                    dc_data.append((ff.name, _quickdump(val)))

    game_dict['key'] = (summary.key, f'https://overtrack-overwatch-games.s3.amazonaws.com/{summary.key}.json')

    return {
        'Summary': list(summary_dict.items()),
        'Game': list(game_dict.items()),
        'Extras': extras,
    }
