import datetime
import json
import logging
from typing import Any, Dict
from urllib.parse import urlparse

import boto3
from flask import Blueprint, Request, render_template, request

from apextrack.lib.authentication import check_authentication
from apextrack.lib.opengraph import Meta
from apextrack.lib.session import session
from apextrack.lib.context_processors import image_url
from overtrack_models.apex_game_summary import ApexGameSummary

request: Request = request
logger = logging.getLogger(__name__)
s3 = boto3.client('s3')
logs = boto3.client('logs')
game_blueprint = Blueprint('game', __name__)


def get_summary(key):
    return ApexGameSummary.get(key)


@game_blueprint.route('/game/<path:key>')
def game(key: str):
    summary = get_summary(key)
    logger.info(f'Fetching {summary.url}')

    url = urlparse(summary.url)
    game_object = s3.get_object(
        Bucket=url.netloc.split('.')[0],
        Key=url.path[1:]
    )
    game_data = json.loads(game_object['Body'].read())

    # used for link previews
    og_description = make_game_description(summary, divider='\n')
    meta = Meta(
        title=f'{game_data["squad"]["player"]["name"]} placed #{summary.placed}',  # TODO: find another way of getting the name,
        description=og_description,
        colour={
            1: '#ffdf00',
            2: '#ef20ff',
            3: '#d95ff'
        }.get(summary.placed, '#992e26'),
        image_url=image_url(game_data['squad']['player']['champion'])
    )

    if check_authentication() is None and session.superuser:
        try:
            admin_data = get_admin_data(summary, game_object)
        except:
            logger.exception('Failed to get admin data for game')
            admin_data = None
    else:
        admin_data = None

    return render_template(
        'game/game.html',
        summary=summary,
        game=game_data,
        is_ranked=summary.rank is not None,

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
    if 'frames' in game_object['Metadata']:
        frames_url = urlparse(game_object['Metadata']['frames'])
        frames_object = s3.get_object(
            Bucket=frames_url.netloc,
            Key=frames_url.path[1:]
        )
        frames_metadata = frames_object['Metadata']
        if 'log' in frames_metadata:
            del frames_metadata['log']  # already have this
        frames_metadata['_href'] = s3.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': frames_url.netloc,
                'Key': frames_url.path[1:]
            }
        )

    else:
        frames_metadata = None

    if 'log' in game_object['Metadata'] and 'start' in game_object['Metadata']['log']:
        log_url = urlparse(game_object['Metadata']['log'])
        log_params = dict(e.split('=') for e in log_url.fragment.split(':', 1)[1].split(';'))

        log_time = datetime.datetime.strptime(log_params['start'], "%Y-%m-%dT%H:%M:%SZ")
        tz_offset = datetime.datetime.now() - datetime.datetime.utcnow()
        log_data = logs.get_log_events(
            logGroupName=log_params['group'],
            logStreamName=log_params['stream'],
            startTime=int((log_time + tz_offset).timestamp() * 1000)
        )
        log_lines = []
        for i, e in enumerate(log_data['events']):
            log_lines.append(e['message'].strip())
            if i > 10 and 'END RequestId' in e['message']:
                break
    else:
        log_lines = []

    game_metadata = game_object['Metadata']
    game_metadata['_href'] = summary.url

    return {
        'game_metadata': game_metadata,
        'frames_metadata': frames_metadata,
        'log': log_lines
    }

