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
    cached_apex_games = get_mock_data()

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


def get_mock_data() -> List[ApexGameSummary]:
    cache_path = os.path.join(tempfile.gettempdir(), 'apex_games.json')
    logger.info(f'Cache path is {cache_path}')
    try:
        with open(cache_path) as f:
            logger.info(f'Loading cached games')
            data = json.load(f)
            if data['source'] != GAMES_SOURCE:
                raise ValueError('Cache is for wrong account')
            cached_apex_games = [
                ApexGameSummary(**g) for g in data['games']
            ]
    except Exception as e:
        logger.warning(f'Unable to load cached apex games - downloading')
        next_key = True
        _games = []
        while next_key:
            url = 'https://api2.overtrack.gg/apex/games/' + GAMES_SOURCE + '?limit=500'
            if isinstance(next_key, str):
                url += '&last_evaluated_key=' + next_key
            logger.info(f'Downloading page {url}')
            r = requests.get(url)
            print(r.status_code)
            r.raise_for_status()
            data = r.json()

            logger.info(f'Got {len(data["games"])} games')
            _games += data['games']
            next_key = data['last_evaluated_key']
            print(next_key)

        cached_apex_games = [
            ApexGameSummary(**g) for g in _games
        ]

        logger.info(f'Caching games')
        with open(cache_path, 'w') as f:
            json.dump({
                'games': _games,
                'source': GAMES_SOURCE
            }, f, indent=2)

    for g in cached_apex_games:
        g.user_id = mock_user.user_id

    return cached_apex_games
