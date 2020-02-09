import json
import logging
import os
import tempfile
from typing import List

import requests

from overtrack_models.orm.overwatch_game_summary import OverwatchGameSummary
from overtrack_web.mocks.dynamo_mocks import MockIndex
from overtrack_web.mocks.login_mocks import mock_user

GAMES_SOURCE = os.environ.get('OVERWATCH_GAMES_SOURCE', 'eeveea')

logger = logging.getLogger(__name__)


def mock_overwatch_games():
    cached_overwatch_games = get_mock_data()

    primary_index = MockIndex(
        cached_overwatch_games,
        'key'
    )
    OverwatchGameSummary.query = primary_index.query
    OverwatchGameSummary.scan = primary_index.scan
    OverwatchGameSummary.get = primary_index.get

    OverwatchGameSummary.user_id_time_index = MockIndex(
        cached_overwatch_games,
        'user_id'
    )


def get_mock_data() -> List[OverwatchGameSummary]:
    cache_path = os.path.join(tempfile.gettempdir(), 'overwatch_games.json')
    logger.info(f'Cache path is {cache_path}')
    try:
        with open(cache_path) as f:
            logger.info(f'Loading cached games')
            data = json.load(f)
            if data['source'] != GAMES_SOURCE:
                raise ValueError('Cache is for wrong account')
            cached_overwatch_games = [
                OverwatchGameSummary(**g) for g in data['games']
            ]
    except Exception as e:
        logger.warning(f'Unable to load cached overwatch games - downloading')
        games = []
        for season_id in mock_user.overwatch_seasons:
            next_key = True
            while next_key:
                url = f'https://api2.overtrack.gg/overwatch/games/{GAMES_SOURCE}?season={season_id}&limit=500'
                if isinstance(next_key, str):
                    url += '&last_evaluated_key=' + next_key
                logger.info(f'Downloading page {url}')
                r = requests.get(url)
                r.raise_for_status()
                data = r.json()

                logger.info(f'Got {len(data["games"])} games')
                for g in data['games']:
                    g['season'] = g['season_index']
                    del g['season_index']
                    del g['url']
                    games.append(g)
                next_key = data['last_evaluated_key']

        cached_overwatch_games = [
            OverwatchGameSummary(**g) for g in games
        ]

        logger.info(f'Caching games')
        with open(cache_path, 'w') as f:
            json.dump({
                'games': games,
                'source': GAMES_SOURCE
            }, f, indent=2)

    for g in cached_overwatch_games:
        g.user_id = mock_user.user_id

    return cached_overwatch_games
