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
    0: Season(name='Unknown Season', start=1, end=2000000000, index=None, is_222=True)
}
try:
    r = requests.get('https://api2.overtrack.gg/data/overwatch/seasons')
    r.raise_for_status()
    seasons = {s.index: s for s in typedload.load(r.json()['seasons'], List[Season])}
    logger.info(f'Downloaded overwatch season data: {len(seasons)} seasons')
except:
    logger.exception(f'Failed to fetch overwatch season data')

current_season = seasons[sorted(seasons.keys())[-1]]


StatType = Literal['maximum', 'average', 'best', 'duration']
Role = Literal['tank', 'damage', 'support']


heroes: Dict[str, Hero] = {}
try:
    r = requests.get('https://api2.overtrack.gg/data/overwatch/heroes')
    r.raise_for_status()
    heroes = typedload.load(r.json(), Dict[str, Hero])
    logger.info(f'Downloaded overwatch hero data: {len(heroes)} heroes')
except:
    logger.exception(f'Failed to fetch overwatch hero data')

hero_colors = {
    "ana": "#718ab3",
    "ashe": "#666769",
    "baptiste": "#57b2cb",
    "bastion": "#7c8f7b",
    "brigitte": "#be736e",
    "doomfist": "#815049",
    "dva": "#ed93c7",
    "genji": "#97ef43",
    "hammond": "#db9342",
    "hanzo": "#b9b48a",
    "junkrat": "#ecbd53",
    "lucio": "#85c952",
    "mccree": "#ae595c",
    "mei": "#6faced",
    "mercy": "#ebe8bb",
    "moira": "#803c51",
    "orisa": "#468c43",
    "pharah": "#3e7dca",
    "reaper": "#7d3e51",
    "reinhardt": "#929da3",
    "roadhog": "#b68c52",
    "sigma": "#94a1a6",
    "soldier": "#697794",
    "sombra": "#7359ba",
    "symmetra": "#8ebccc",
    "torbjorn": "#c0726e",
    "tracer": "#d79342",
    "widowmaker": "#9e6aa8",
    "winston": "#a2a6bf",
    "zarya": "#e77eb6",
    "zenyatta": "#ede582",
}


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
