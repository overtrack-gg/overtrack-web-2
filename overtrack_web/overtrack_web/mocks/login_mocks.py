import datetime
import random
from typing import List, NamedTuple, Optional

from flask import g

from overtrack_web.data import apex_data, overwatch_data
from overtrack_web.lib import authentication


valorant_games_public: Optional[bool] = None


class MockUser(NamedTuple):
    username: str = 'MOCK_USER'
    user_id: int = 0

    apex_last_season: int = apex_data.current_season.index
    apex_last_game_ranked: bool = True
    apex_seasons: List[int] = list(apex_data.seasons.keys())
    apex_games: int = 1

    overwatch_last_season: int = overwatch_data.current_season.index
    overwatch_seasons: List[int] = list(overwatch_data.seasons.keys())[-5:]
    overwatch_games: int = 1

    valorant_games: int = 1

    subscription_active: bool = False # bool(random.randint(0, 1))
    trial_active: bool = False # not subscription_active and bool(random.randint(0, 1))
    trial_games_remaining: int = random.randint(1, 30)
    trial_end_time: float = datetime.datetime.now().timestamp() + random.randint(0, 30 * 24 * 60 * 60)
    superuser: bool = True

    trial_valid: bool = True

    @property
    def valorant_games_public(self) -> Optional[bool]:
        global valorant_games_public
        return valorant_games_public

    @valorant_games_public.setter
    def valorant_games_public(self, value: bool) -> None:
        global valorant_games_public
        valorant_games_public = value

    def refresh(self):
        pass

    def save(self) -> None:
        pass

mock_user = MockUser()

class MockSession(NamedTuple):
    user_id: int
    key: str
    superuser: bool = False
    user: MockUser = mock_user

def mock_check_authentication(*_, **__):
    g.session = MockSession(
        user_id=-1,
        key='MOCK-USER'
    )
    return None
authentication.check_authentication = mock_check_authentication
