import datetime
import logging
from pprint import pformat, pprint
from typing import Tuple, Dict, Optional

import requests
from dataclasses import dataclass
from overtrack_models.dataclasses import typedload

logger = logging.getLogger(__name__)


@dataclass
class ApexRankSummary:
    rp: int
    floor: int
    ceil: int
    rank: str
    tier: str

    @property
    def uri(self) -> str:
        return 'predator' if self.rank == 'apex predator' else self.rank

    @property
    def color(self) -> str:
        return {
            'bronze': '#402D25',
            'silver': '#444448',
            'gold': '#4d4030',
            'platinum': '#24424a',
            'diamond': '#3a4b9e',
            # TODO: master
            'apex predator': '#8a1f1c',
        }[self.rank]


@dataclass
class ApexSeason:
    index: int
    start: float
    end: float
    season_name: Optional[str] = None
    has_ranked: bool = True

    @property
    def name(self) -> str:
        return self.season_name or f'Season {self.index}'


seasons: Dict[int, ApexSeason] = {
    0: ApexSeason(index=0, start=0.0, end=1553014800.0, has_ranked=False),
    1: ApexSeason(index=1, start=1553014800.0, end=1562086800.0, has_ranked=False),
    2: ApexSeason(index=2, start=1562086800.0, end=1569956446.0),
    3: ApexSeason(index=3, start=1569956446.0, end=1580839200.0),
    4: ApexSeason(index=4, start=1580839200.0, end=1589302800.0),
    5: ApexSeason(index=5, start=1589302800.0, end=1597766400.0),
}
current_season = seasons[sorted(seasons.keys())[-1]]
try:
    logger.info('Fetching season IDs from API')
    response = requests.get('https://api2.overtrack.gg/data/apex/season_ids')
    response.raise_for_status()
    data = response.json()
    seasons = typedload.load(data['seasons'], Dict[int, ApexSeason])
    current_season = typedload.load(data['current_season'], ApexSeason)
    current_season = [s for s in seasons.values() if s == current_season][0]
    for s in seasons.values():
        if s.end == float('inf'):
            s.end = s.start + 10 * 365 * 24 * 60 * 60
    logger.info(f'Got seasons:\n{pformat(seasons)}')
except:
    logger.exception(f'Failed to fetch season IDs - using fallback')

rank_rp = {
    'bronze': (0, 1200),
    'silver': (1200, 2800),
    'gold': (2800, 4800),
    'platinum': (4800, 7200),
    'diamond': (7200, 10_000),
    # TODO: master
    'apex_predator': (10_000, 99_999)
}
def get_tier_window(rp: int, tier_entry: int, tier_step: int) -> Tuple[int, int]:
    return (
        ((rp - tier_entry) // tier_step) * tier_step + tier_entry,
        ((rp - tier_entry) // tier_step + 1) * tier_step + tier_entry
    )

