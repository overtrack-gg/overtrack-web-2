import collections
import hashlib
import json
import logging
import os
from dataclasses import fields, is_dataclass, dataclass
from typing import Tuple, Dict, Any, Optional, List, Union
from urllib.parse import urlparse

import boto3
import requests
from flask import Blueprint, render_template, render_template_string, url_for, request, Response
from itertools import takewhile, dropwhile, zip_longest

from overtrack_models.dataclasses.valorant import ValorantGame, Kill, Round, Ult, Player
from overtrack_models.orm.valorant_game_summary import ValorantGameSummary
from overtrack_web.lib.authentication import check_authentication
from overtrack_web.lib.opengraph import Meta
from overtrack_web.lib.session import session
from overtrack_web.views.valorant.games_list import OLDEST_SUPPORTED_GAME_VERSION

GAMES_BUCKET = 'overtrack-valorant-games'
COLOURS = {
    'WIN': '#58a18e',
    'LOSS': '#e35e5b',
    'SCRIM': '#DDCE7A',
}

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

    if game.won is not None:
        result = ['LOSS', 'WIN'][game.won]
    elif game.rounds.has_game_resets:
        result = 'SCRIM'
    else:
        result = 'game'

    if game.teams.firstperson:
        title = f'{game.teams.firstperson.name}\'s {result} on {game.map}'
    else:
        title = f'{result[0].capitalize() + result[1:]} on {game.map}'

    imagehash = hashlib.md5(str((game.won, game.game_mode, game.rounds.final_score, summary.agent)).encode()).hexdigest()

    def is_first_round(round: Round) -> bool:
        return round.attacking == game.rounds.rounds[0].attacking

    rounds_first = takewhile(is_first_round, game.rounds.rounds)
    rounds_second = dropwhile(is_first_round, game.rounds.rounds)

    return render_template(
        'valorant/game/game.html',

        title=title,
        meta=Meta(
            title=title,
            image_url=url_for('valorant.game.game_card_png', key=key, _external=True) + f'?_cachebust={imagehash}',
            twitter_image_url=url_for('valorant.game.game_card_png', key=key, _external=True) + f'?height=190&_cachebust={imagehash}',
            summary_large_image=True,
            colour=COLOURS.get(result, 'gray')
        ),

        summary=summary,
        game=game,
        rounds_combined=list(zip_longest(rounds_first, rounds_second)),

        # show_edit=check_authentication() is None and (summary.user_id == session.user_id or session.superuser),

        dev_info=dev_info,
    )


@game_blueprint.route('<path:key>/card')
def game_card(key: str):
    try:
        game = ValorantGameSummary.get(key)
    except ValorantGameSummary.DoesNotExist:
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
                <body class="games-list">
                    {% include 'valorant/games_list/game_card.html' %}
                </body>
            </html>
        ''',
        title='Card',
        game=game,
        show_rank=True,

        OLDEST_SUPPORTED_GAME_VERSION=OLDEST_SUPPORTED_GAME_VERSION,
    )


@game_blueprint.route('/<path:key>/card.png')
def game_card_png(key: str):
    if 'RENDERTRON_URL' not in os.environ:
        return 'Rendertron url not set on server', 500

    url = ''.join((
        os.environ['RENDERTRON_URL'],
        'screenshot/',
        url_for('valorant.game.game_card', key=key, _external=True),
        f'?width={min(int(request.args.get("width", 1000)), 2000)}',
        f'&height={min(int(request.args.get("height", 80)), 512)}',
        f'&_cachebust={request.args.get("_cachebust", "")}'
    ))
    try:
        r = requests.get(
            url,
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
def context_processor() -> Dict[str, Any]:
    return {
        'game_name': 'valorant',
    }


# ----- Template Variables -----


@game_blueprint.app_template_filter('score')
def score_template_filter(score: Optional[Tuple[int, int]]) -> str:
    if not score:
        return '?-?'
    else:
        return f'{score[0]}-{score[1]}'


# ----- Template Filters -----

@game_blueprint.app_template_filter('percentage')
def percentage(frac: Optional[float]) -> str:
    return f'{frac * 100:.0f}%' if frac is not None else '-'


@game_blueprint.app_template_filter('weapon_name')
def weapon_name(s: str) -> str:
    if s == 'null':
        return '?'
    else:
        return s.split('.', 1)[-1].replace('_', ' ').title()


@game_blueprint.app_template_filter('get_kill_counts')
def get_kill_counts(weapons: Dict[Optional[str], List[Kill]]):
    return sorted(
        [
            (
                w,
                len(ks),
                f'{len([k for k in ks if k.headshot]) / len(ks):.0%}',
                f'{len([k for k in ks if k.wallbang]) / len(ks):.0%}',
            ) for (w, ks) in weapons.items()
        ],
        key=lambda e: e[1],
        reverse=True,
    )


@dataclass
class SpikePlantedEvent:
    round_timestamp: float
    planter: Player


@game_blueprint.app_template_filter('round_events')
def round_events(round: Round) -> List[Union[Kill, Ult]]:
    events = round.kills.kills + round.ults_used
    if round.spike_planted:
        events.append(SpikePlantedEvent(round.spike_planted, round.spike_planter))
    events.sort(
        key=lambda e: e.round_timestamp if hasattr(e, 'round_timestamp') else e.round_lost_timestamp
    )
    return events


@game_blueprint.app_template_test('kill')
def is_kill(e):
    return isinstance(e, Kill)


@game_blueprint.app_template_test('ult')
def is_ult(e):
    return isinstance(e, Ult)


@game_blueprint.app_template_test('plant')
def is_plant(e):
    return isinstance(e, SpikePlantedEvent)


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

    return ValorantGame.from_dict(game_data), metadata


# ----- Utility Functions -----


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
            extras['kills'].append(('\u00a0' * 6 + f'{i}', repr(k)))
    game_dict['key'] = (summary.key, f'https://overtrack-valorant-games.s3.amazonaws.com/{summary.key}.json')
    if game_dict.get('vod'):
        game_dict['vod'] = (game_dict['vod'], game_dict['vod'])

    return {
        'Summary': list(summary_dict.items()),
        'Game': list(game_dict.items()),
        'Extras': extras,
    }
