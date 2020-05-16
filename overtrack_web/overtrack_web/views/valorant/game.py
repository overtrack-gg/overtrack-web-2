import collections
import itertools
import json
import logging
import random
from typing import Tuple, Dict, Any, Optional, List
from urllib.parse import urlparse

import boto3
import requests
from dataclasses import fields, is_dataclass, dataclass
from flask import Blueprint, render_template
from overtrack_models.dataclasses.typedload import referenced_typedload
from overtrack_models.dataclasses.valorant import ValorantGame, Kill, Player, Round
from overtrack_models.orm.valorant_game_summary import ValorantGameSummary

from overtrack_web.lib.authentication import check_authentication
from overtrack_web.lib.session import session

GAMES_BUCKET = 'overtrack-valorant-games'

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
game_blueprint = Blueprint('valorant.game', __name__)


@game_blueprint.route('/<path:key>')
def game(key: str):
    try:
        summary = ValorantGameSummary.get(key)
    except ValorantGameSummary.DoesNotExist:
        return 'Game does not exist', 404

    game, metadata = load_game(summary)
    dev_info = get_dev_info(summary, game, metadata)

    if game.teams.firstperson and game.won is not None:
        title = f'{game.teams.firstperson.name}\'s {["LOSS", "WIN"][game.won]} on {game.map}'
    elif game.teams.firstperson:
        title = f'{game.teams.firstperson.name}\'s game on {game.map}'
    elif game.won is not None:
        title = f'{["LOSS", "WIN"][game.won]} on {game.map}'
    else:
        title = f'Game on {game.map}'

    return render_template(
        'valorant/game/game.html',

        title=title,
        # meta=Meta(
        #     title=title,
        #     image_url=url_for('overwatch.game.game_card_png', key=key, _external=True) + f'?_cachebust={imagehash}',
        #     twitter_image_url=url_for('overwatch.game.game_card_png', key=key, _external=True) + f'?height=190&_cachebust={imagehash}',
        #     summary_large_image=True,
        #     colour=COLOURS.get(game.result, 'gray')
        # ),

        summary=summary,
        game=game,

        # show_edit=check_authentication() is None and (summary.user_id == session.user_id or session.superuser),

        dev_info=dev_info,
    )


# ----- Template Variables -----

@game_blueprint.context_processor
def context_processor() -> Dict[str, Any]:
    return {
        'game_name': 'valorant',
        'example_exposed_function': example_exposed_function,
    }


def example_exposed_function():
    return random.choice(['foo', 'bar', 'baz'])


# ----- Template Filters -----

@game_blueprint.app_template_filter('score')
def score_template_filter(score: Optional[Tuple[int, int]]) -> str:
    if not score:
        return '?-?'
    else:
        return f'{score[0]}-{score[1]}'

# @game_blueprint.app_template_filter('killson')
# def killson(kills: List[Kill], player: Player) -> List[Kill]:
#     print('killson', player, kills)
#     return [k for k in kills if k.killed == player]
#
# @game_blueprint.app_template_filter('deathsby')
# def deathsby(kills: List[Kill], player: Player) -> List[Kill]:
#     return [k for k in kills if k.killer == player]

@game_blueprint.app_template_filter('percentage')
def percentage(frac: Optional[float]) -> str:
    return f'{frac * 100:.0f}%' if frac is not None else '-'

@game_blueprint.app_template_filter('weapon_name')
def weapon_name(s: str) -> str:
    return s.split('.', 1)[-1].replace('_', ' ').title()

@game_blueprint.app_template_filter('get_kill_counts')
def get_kill_counts(weapons):
    return sorted(
        [(w, len(ks)) for (w, ks) in weapons.items()],
        key=lambda e: e[1],
        reverse=True,
    )


# ----- Utility Functions -----

def load_game(summary: ValorantGameSummary) -> Tuple[ValorantGame, Dict]:
    try:
        game_object = s3.get_object(
            Bucket=GAMES_BUCKET,
            Key=summary.key + '.json'
        )
        game_data = json.loads(game_object['Body'].read())
        metadata = game_object['Metadata']
    except:
        if s3:
            logger.exception('Failed to fetch game data from S3 - trying HTTP')
        r = requests.get(f'https://{GAMES_BUCKET}.s3.amazonaws.com/{summary.key}.json')
        r.raise_for_status()
        game_data = r.json()
        metadata = {}

    return referenced_typedload.load(game_data, ValorantGame), metadata


def get_dev_info(summary, game, metatada):
    if check_authentication() is not None or not session.user.superuser:
        return None

    summary_dict = summary.asdict()
    summary_dict['key'] = (summary.key, f'https://overtrack-valorant-games.s3.amazonaws.com/{summary.key}.json')
    log = metatada.get('log')
    if log:
        metatada['log'] = (
            ' '.join(log.split(':', 3)[2].split(';')),
            log,
        )

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
        if not isinstance(val, (tuple, str)) and isinstance(val, collections.Sequence):
            return f'... {len(val)} items'
        else:
            rep = repr(val)
            if len(rep) < 50:
                return rep
            else:
                return rep[:50 - 3] + '...'

    game_dict = {}
    extras = {
        'metadata': metatada.items(),
    }
    for f in fields(game):
        if f.name == 'images':
            game_dict['images'] = ''
            for image in game.images:
                game_dict['\u00a0' * 6 + '.' + image] = (game.images[image].rsplit('/', 1)[-1], game.images[image])
        elif not is_dataclass(getattr(game, f.name)):
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

    extras['kills'] = []
    for r in game.rounds:
        extras['kills'].append((f'Round\u00a0{r.index}', ''))
        for i, k in enumerate(r.kills):
            extras['kills'].append(('\u00a0' * 6 + f'{i}', str(k)))
    game_dict['key'] = (summary.key, f'https://overtrack-valorant-games.s3.amazonaws.com/{summary.key}.json')

    return {
        'Summary': list(summary_dict.items()),
        'Game': list(game_dict.items()),
        'Extras': extras,
    }
