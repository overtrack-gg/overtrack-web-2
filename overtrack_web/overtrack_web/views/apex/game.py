import datetime
import json
import logging
from typing import Any, Dict, List
from urllib.parse import urlparse

import boto3
import dataclasses
import requests
import time
from dataclasses import dataclass
from flask import Blueprint, Request, render_template, request

from overtrack_models.dataclasses import typedload
from overtrack_models.dataclasses.apex.apex_game import ApexGame
from overtrack_models.orm.apex_game_summary import ApexGameSummary
from overtrack_web.lib.authentication import check_authentication
from overtrack_web.lib.context_processors import image_url
from overtrack_web.lib.opengraph import Meta
from overtrack_web.lib.session import session


request: Request = request
logger = logging.getLogger(__name__)
try:
    s3 = boto3.client('s3')
    """ :type s3: mypy_boto3.s3.Client """
    s3.list_objects_v2(Bucket='overtrack-apex-games')
except:
    logger.exception('Failed to create AWS S3 client - fetching games over HTTP')
    s3 = None
try:
    logs = boto3.client('logs')
    """ :type s3: mypy_boto3.logs.Client """
except:
    logger.exception('Failed to create AWS logs client - running without admin logs')
    logs = None

game_blueprint = Blueprint('apex.game', __name__)


@game_blueprint.context_processor
def context_processor():
    return {
        'game_name': 'apex'
    }


@dataclass
class ScrimDetails:
    champion_name: str
    scrims_name: str
    other_games: List[List[ApexGameSummary]]


@game_blueprint.route('/<path:key>')
def game(key: str):
    try:
        summary = ApexGameSummary.get(key)
    except ApexGameSummary.DoesNotExist:
        return 'Game does not exist', 404
    logger.info(f'Fetching {summary.url}')

    try:
        url = urlparse(summary.url)
        game_object = s3.get_object(
            Bucket=url.netloc.split('.')[0],
            Key=url.path[1:]
        )
        game_data = json.loads(game_object['Body'].read())
    except:
        game_object = None
        logger.exception('Failed to fetch game data from S3 - trying HTTP')
        r = requests.get(summary.url)
        r.raise_for_status()
        game_data = r.json()

    game_data = compat_game_data(game_data)
    game = typedload.load(game_data, ApexGame)

    # used for link previews
    og_description = make_game_description(summary, divider='\n')
    meta = Meta(
        title=f'{game.squad.player.name} placed #{summary.placed}',  # TODO: find another way of getting the name,
        description=og_description,
        colour={
            1: '#ffdf00',
            2: '#ef20ff',
            3: '#d95ff'
        }.get(summary.placed, '#992e26'),
        image_url=image_url(game.squad.player.champion)
    )

    scrim_details = None
    if summary.scrims and summary.match_id and game.match_id:
        champion_name = (game.champion or {}).get('ocr_name') or summary.match_id.split('/')[1]
        matching_games = []
        for match_id in game.match_ids:
            logger.info(f'Checking for matching scrims with match_id={match_id}')
            for other_game in ApexGameSummary.match_id_index.query(
                match_id,
                (ApexGameSummary.scrims == summary.scrims)# & (ApexGameSummary.key != summary.key)
            ):
                if not any(any(other_game.key == g.key for g in gs) for gs in matching_games):
                    for gamesets in matching_games:
                        if any(g.placed == other_game.placed for g in gamesets):
                            gamesets.append(other_game)
                            break
                    else:
                        matching_games.append([other_game])

        # TODO: dedupe
        # for g in matching_games:
        #     g.player_name = ' / '.join(filter(None, [g.player_name] + list(g.squadmate_names or ())))
        scrim_details = ScrimDetails(
            champion_name,
            'Mendo Scrims (Beta)',
            sorted(matching_games, key=lambda gs: gs[0].placed),
        )
    logger.info(f'Scrim details: {scrim_details}')

    if logs and check_authentication() is None and session.superuser and game_object:
        try:
            admin_data = get_admin_data(summary, game_object)
        except:
            logger.exception('Failed to get admin data for game')
            admin_data = None
    else:
        admin_data = None

    return render_template(
        'apex/game/game.html',
        summary=summary,
        game=game,
        is_ranked=summary.rank is not None,

        scrim_details=scrim_details,

        meta=meta,

        admin_data=admin_data
    )


def make_game_description(summary: ApexGameSummary, divider: str = '\n', include_knockdowns: bool = False) -> str:
    og_description = f'{summary.kills} Kills'
    if include_knockdowns and summary.knockdowns:
        og_description += f'{divider}{summary.knockdowns} Knockdowns'
    if summary.squad_kills:
        og_description += f'{divider}{summary.squad_kills} Squad Kills'
    if summary.landed != 'Unknown':
        og_description += f'{divider}Dropped {summary.landed}'
    return og_description


def get_admin_data(summary: ApexGameSummary, game_object: Dict[str, Any]) -> Dict[str, Any]:
    if 'log' in game_object['Metadata'] and 'start' in game_object['Metadata']['log']:
        log_url = urlparse(game_object['Metadata']['log'])
        log_params = dict(e.split('=') for e in log_url.fragment.split(':', 1)[1].split(';'))

        log_time = datetime.datetime.strptime(log_params['start'], "%Y-%m-%dT%H:%M:%SZ")
        tz_offset = datetime.datetime.now() - datetime.datetime.utcnow()
        log_lines = []
        # log_data = logs.get_log_events(
        #     logGroupName=log_params['group'],
        #     logStreamName=log_params['stream'],
        #     startTime=int((log_time + tz_offset).timestamp() * 1000)
        # )
        # for i, e in enumerate(log_data['events']):
        #     log_lines.append(e['message'].strip())
        #     if i > 10 and 'END RequestId' in e['message']:
        #         break
    else:
        log_lines = []

    game_metadata = game_object['Metadata']
    summary_dict = summary.asdict()

    summary_dict['url'] = (summary_dict['url'], summary_dict['url'])

    if 'frames' in game_object['Metadata']:
        frames_url = urlparse(game_object['Metadata']['frames'])
        game_metadata['frames'] = (
            game_metadata['frames'],
            s3.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': frames_url.netloc,
                    'Key': frames_url.path[1:]
                }
            )
        )

        if 'metadata' in game_object['Metadata']:
            metadata_url = urlparse(game_object['Metadata']['metadata'])
            game_metadata['metadata'] = (
                game_metadata['metadata'],
                s3.generate_presigned_url(
                    'get_object',
                    Params={
                        'Bucket': metadata_url.netloc,
                        'Key': metadata_url.path[1:]
                    }
                )
            )

        game_metadata['log'] = (
            urlparse(game_metadata['log']).fragment,
            game_metadata['log']
        )

    return {
        'game_metadata': game_metadata,
        'summary': summary_dict,
        'log': log_lines
    }


def compat_game_data(game_data: Dict[str, Any]) -> Dict[str, Any]:
    game_data = dict(game_data)

    if 'match_started' not in game_data:
        game_data['match_started'] = game_data['timestamp']

    if 'match_id' not in game_data:
        game_data['match_id'] = None
        game_data['match_ids'] = []

    if 'rings' not in game_data['route']:
        game_data['route']['rings'] = []

    return game_data
