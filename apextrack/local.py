import logging
from functools import wraps
from typing import NamedTuple, Dict, Optional, Tuple

import requests

SAMPLE_KEY = 'mendokusaii'


logger = logging.getLogger(__name__)


def check_authentication(*args, **kwargs):
    return None


def require_authentication(_endpoint=None, *args, **kwargs):
    def wrap(endpoint):
        @wraps(endpoint)
        def check_auth(*args, **kwargs):
            return endpoint(*args, **kwargs)

        return check_auth

    if _endpoint is None:
        return wrap
    else:
        return wrap(_endpoint)


class User(NamedTuple):
    user_id: int
    apex_last_season: int = 2
    apex_last_game_ranked: bool = True


class Session(NamedTuple):
    user_id: int
    key: str
    user: User
    superuser: bool = False


session = Session(0, 'local', User(0), False)


# Instead of using the database, just implement the API needed and forward requests to api2.overtrack.gg

requests_session = requests.Session()


class Filter(NamedTuple):
    key: Optional[str]
    type: str
    value1: Optional[object] = None
    value2: Optional[object] = None

    def __and__(self, other):
        return Filter(None, 'and', self, other)

    def __call__(self, game_json):
        if self.type == 'between':
            return self.value1 < game_json[self.key] < self.value2
        elif self.type == 'exists':
            return self.key in game_json and game_json[self.key] is not None
        elif self.type == 'does_not_exist':
            return self.key not in game_json or game_json[self.key] is None
        elif self.type == 'lt':
            return self.key in game_json and game_json[self.key] < self.value1
        elif self.type == 'and':
            return self.value1(game_json) and self.value2(game_json)


class FilterableField:
    """
    Quick and dirty method for supporting query filters
    """
    def __init__(self, name: str):
        self.name = name

    def between(self, a: int, b: int) -> Tuple[str, str, int, int]:
        return Filter(self.name, 'between', a, b)

    def exists(self) -> Tuple[str, str]:
        return Filter(self.name, 'exists')

    def does_not_exist(self) -> Tuple[str, str]:
        return Filter(self.name, 'does_not_exist')

    def __lt__(self, a: int):
        return Filter(self.name, 'lt', a)


class Rank:
    def __init__(self, data: Dict):
        self.rank = data['rank']
        self.tier = data['tier']
        self.rp = data['rp']
        self.rp_change = data['rp_change']


class ApexGameSummary:
    """
    Mock implementation of the ApexGameSummary table where queries/gets just use api2.overtrack.gg
    """
    def __init__(self, data: Dict):
        self.champion = data['champion']
        self.duration = data['duration']
        self.key = data['key']
        self.kills = data['kills']
        self.knockdowns = data['knockdowns']
        self.landed = data['landed']
        self.placed = data['placed']
        self.rank = Rank(data['rank']) if data['rank'] else None
        self.season = data['season']
        self.source = data['source']
        self.squad_kills = data['squad_kills']
        self.squadmates = data['squadmates']
        self.timestamp = data['timestamp']
        self.url = data['url']
        self.user_id = data['user_id']

    @classmethod
    def get(cls, key: str) -> 'ApexGameSummary':
        r = requests_session.get(
            f'https://api2.overtrack.gg/apex/game_summary/{key}',
        )
        r.raise_for_status()
        return cls(r.json())

    timestamp = FilterableField('timestamp')
    rank = FilterableField('rank')
    season = FilterableField('season')


class UserIdTimeIndex:
    """
    Mock implementation of the UserIdTimeIndex supporting inefficient-but-correct filtering semantics
    """
    def query(self, user_id, range_key_condition=None, filter_condition=None, newest_first: bool = False, limit: Optional[int] = None):
        if not newest_first:
            raise NotImplementedError(f'{self.__class__.__name__}.query only implemented for newest_first=True')

        logger.info(f'query({user_id}, {range_key_condition}, {filter_condition})')

        r = requests_session.get(
            f'https://api2.overtrack.gg/apex/games/{SAMPLE_KEY}' + (f'?limit={limit}' if limit else '')
        )
        r.raise_for_status()
        for game_json in r.json()['games']:

            for condition in range_key_condition, filter_condition:
                if condition and not condition(game_json):
                    break
            else:
                yield ApexGameSummary(game_json)


ApexGameSummary.user_id_time_index = UserIdTimeIndex()
