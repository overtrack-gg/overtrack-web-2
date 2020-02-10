import json
import logging
from urllib.parse import urlparse

import boto3
import requests
from dataclasses import fields, is_dataclass, asdict
from flask import Blueprint, Request, render_template, request
from overtrack_models.dataclasses.overwatch.overwatch_game import OverwatchGame

from overtrack_models.dataclasses.typedload import referenced_typedload

from overtrack_models.orm.overwatch_game_summary import OverwatchGameSummary

request: Request = request
logger = logging.getLogger(__name__)
try:
    s3 = boto3.client('s3')
    """ :type s3: boto3_type_annotations.s3.Client """
except:
    logger.exception('Failed to create AWS S3 client - running without admin logs')
    s3 = None
try:
    logs = boto3.client('logs')
    """ :type s3: boto3_type_annotations.s3.Client """
except:
    logger.exception('Failed to create AWS logs client - running without admin logs')
    logs = None

game_blueprint = Blueprint('overwatch.game', __name__)


@game_blueprint.context_processor
def context_processor():
    return {
        'game_name': 'overwatch'
    }


@game_blueprint.route('/<path:key>')
def game(key: str):
    summary = OverwatchGameSummary.get(key)

    try:
        game_object = s3.get_object(
            Bucket='overtrack-overwatch-games',
            Key=summary.key + '.json'
        )
        game_data = json.loads(game_object['Body'].read())
    except:
        game_object = None
        logger.exception('Failed to fetch game data from S3 - trying HTTP')
        r = requests.get(f'https://overtrack-overwatch-games.s3.amazonaws.com/{ summary.key }.json')
        r.raise_for_status()
        game_data = r.json()

    game = referenced_typedload.load(game_data, OverwatchGame)

    game_dict = {}
    for f in fields(game):
        if not is_dataclass(getattr(game, f.name)):
            game_dict[f.name] = getattr(game, f.name)

    return render_template(
        'overwatch/game/game.html',

        game=game,

        summary_dict=summary.asdict(),
        game_dict=game_dict,

        all_stats=asdict(game.stats.stats['all heroes'])
    )
