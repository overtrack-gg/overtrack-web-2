import json
import logging
import os
import tempfile
from typing import List, Optional, Tuple

import requests

import overtrack_web
from overtrack_models.orm.valorant_game_summary import ValorantGameSummary
from overtrack_models.queries.valorant.winrates import MapAgentWinrates
from overtrack_web.lib import queries

from overtrack_web.mocks.dynamo_mocks import MockIndex
from overtrack_web.mocks.login_mocks import mock_user

GAMES_SOURCE = os.environ.get('VALORANT_GAMES_SOURCE', 'mendo')

logger = logging.getLogger(__name__)


def mock_valorant_games():
    cached_valorant_games = download_games_list()

    primary_index = MockIndex(
        cached_valorant_games,
        'key',
        ValorantGameSummary,
    )
    ValorantGameSummary.query = primary_index.query
    ValorantGameSummary.scan = primary_index.scan
    ValorantGameSummary.get = primary_index.get

    ValorantGameSummary.user_id_timestamp_index = MockIndex(
        cached_valorant_games,
        'user_id',
        ValorantGameSummary,
    )


def download_games_list() -> List[ValorantGameSummary]:
    games = []
    next_key = True
    while next_key:
        url = 'https://api2.overtrack.gg/valorant/games/' + GAMES_SOURCE + '?limit=500'
        if isinstance(next_key, str):
            url += '&last_evaluated_key=' + next_key
        logger.info(f'Downloading games list: {url}')
        r = requests.get(url)
        r.raise_for_status()
        data = r.json()

        games += data['games']
        next_key = data['last_evaluated_key']

    cached_valorant_games = [
        ValorantGameSummary(**g) for g in games
    ]

    for g in cached_valorant_games:
        g.user_id = mock_user.user_id

    return cached_valorant_games


def mock_valorant_winrates() -> None:
    average_winrates, user_winrates = get_mock_valorant_winrates()

    queries.valorant.get_average_winrates = lambda: average_winrates
    queries.valorant.get_winrates = lambda _: user_winrates


def get_mock_valorant_winrates() -> Tuple[MapAgentWinrates, MapAgentWinrates]:
    average_winrates = MapAgentWinrates.from_dict(
        requests.get('https://api2.overtrack.gg/valorant/winrates/all').json()
    )
    user_winrates = MapAgentWinrates.from_dict(
        requests.get('https://api2.overtrack.gg/valorant/winrates/' + GAMES_SOURCE).json()
    )

    return average_winrates, user_winrates
