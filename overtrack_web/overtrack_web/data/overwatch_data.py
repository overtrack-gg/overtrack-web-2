import logging
from typing import List, Optional, Tuple, Dict

import requests
from dataclasses import dataclass
from overtrack_models.dataclasses.overwatch.basic_types import Hero

from overtrack_models.dataclasses import Literal
from overtrack_models.dataclasses.typedload import typedload


logger = logging.getLogger(__name__)


@dataclass
class Season:
    name: str
    start: float
    end: float

    index: Optional[int] = None
    display: bool = True
    off_season: bool = False
    is_222: bool = True

    def __contains__(self, timestamp: float) -> bool:
        return self.start <= timestamp < self.end


seasons = {
    4: Season(name='Season 4', start=1488193200, end=1496059200, index=4, is_222=False),
    5: Season(name='Season 5', start=1496275199, end=1503964799, index=5, is_222=False),
    6: Season(name='Season 6', start=1504224000, end=1509237000, index=6, is_222=False),
    7: Season(name='Season 7', start=1509494400, end=1514458800, index=7, is_222=False),
    8: Season(name='Season 8', start=1514764800, end=1519556400, index=8, is_222=False),
    9: Season(name='Season 9', start=1519862400, end=1524875400, index=9, is_222=False),
    10: Season(name='Season 10', start=1525132800, end=1530144600, index=10, is_222=False),
    11: Season(name='Season 11', start=1530403170, end=1535501400, index=11, is_222=False),
    12: Season(name='Season 12', start=1535759970, end=1540768200, index=12, is_222=False),
    13: Season(name='Season 13', start=1541026770, end=1546293600, index=13, is_222=False),
    14: Season(name='Season 14', start=1546300800, end=1551398400, index=14, is_222=False),
    15: Season(name='Season 15', start=1551398400, end=1556668800, index=15, is_222=False),
    16: Season(name='Season 16', start=1556668800, end=1561939200, index=16, is_222=False),
    17: Season(name='Season 17', start=1561939200, end=1565712000, index=17, is_222=False),
    18: Season(name='Season 18', start=1567467600, end=1573149600, index=18, is_222=True),
    19: Season(name='Season 19', start=1573149600, end=1577988000, index=19, is_222=True),
    20: Season(name='Season 20', start=1577988000, end=1583431200, index=20, is_222=True),
}
current_season = seasons[sorted(seasons.keys())[-1]]
# TODO: update seasons from API


StatType = Literal['maximum', 'average', 'best', 'duration']
Role = Literal['tank', 'damage', 'support']


heroes: Dict[str, Hero] = {}
try:
    r = requests.get('https://api2.overtrack.gg/data/overwatch/heroes')
    r.raise_for_status()
    heroes = typedload.load(r.json(), Dict[str, Hero])
except:
    logger.exception(f'Failed to fetch overwatch hero data')


def sr_to_rank(sr: int) -> str:
    if sr < 1500:
        return 'bronze'
    elif sr < 2000:
        return 'silver'
    elif sr < 2500:
        return 'gold'
    elif sr < 3000:
        return 'platinum'
    elif sr < 3500:
        return 'diamond'
    elif sr < 4000:
        return 'master'
    elif sr <= 5000:
        return 'grandmaster'
    else:
        return 'unknown'
