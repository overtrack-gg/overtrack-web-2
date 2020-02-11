import json
import logging
import os
import tempfile
from typing import List

import requests

from overtrack_models.orm.apex_game_summary import ApexGameSummary
from overtrack_web.mocks.dynamo_mocks import MockIndex
from overtrack_web.mocks.login_mocks import mock_user

GAMES_SOURCE = os.environ.get('APEX_GAMES_SOURCE', 'mendokusaii')

logger = logging.getLogger(__name__)


def mock_apex_games():
    cached_apex_games = download_games_list()

    primary_index = MockIndex(
        cached_apex_games,
        'key'
    )
    ApexGameSummary.query = primary_index.query
    ApexGameSummary.scan = primary_index.scan
    ApexGameSummary.get = primary_index.get

    ApexGameSummary.user_id_time_index = MockIndex(
        cached_apex_games,
        'user_id'
    )


def download_games_list() -> List[ApexGameSummary]:
    games = []
    next_key = True
    while next_key:
        url = 'https://api2.overtrack.gg/apex/games/' + GAMES_SOURCE + '?limit=500'
        if isinstance(next_key, str):
            url += '&last_evaluated_key=' + next_key
        logger.info(f'Downloading games list: {url}')
        r = requests.get(url)
        r.raise_for_status()
        data = r.json()

        games += data['games']
        next_key = data['last_evaluated_key']

    cached_apex_games = [
        ApexGameSummary(**g) for g in games
    ]

    for g in cached_apex_games:
        g.user_id = mock_user.user_id

    return cached_apex_games
