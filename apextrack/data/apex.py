import datetime
from typing import Tuple

from dataclasses import dataclass

RANK_RP = {
    'bronze': (0, 1200),
    'silver': (1200, 2800),
    'gold': (2800, 4800),
    'platinum': (4800, 7200),
    'diamond': (7200, 10_000),
    'apex_predator': (10_000, 99_999)
}


def get_tier_window(rp: int, tier_entry: int, tier_step: int) -> Tuple[int, int]:
    return (
        ((rp - tier_entry) // tier_step) * tier_step + tier_entry,
        ((rp - tier_entry) // tier_step + 1) * tier_step + tier_entry
    )


@dataclass
class Season:
    index: int
    start: float
    end: float
    season_name: str = None
    has_ranked: bool = False

    @property
    def name(self) -> str:
        return self.season_name or f'Season {self.index}'


@dataclass
class RankSummary:
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
            'apex predator': '#8a1f1c'
        }[self.rank]


_PDT = datetime.timezone(datetime.timedelta(hours=-7))
_season_1_start = datetime.datetime.strptime(
    # https://twitter.com/PlayApex/status/1107733497450356742
    'Mar 19 2019 10:00AM',
    '%b %d %Y %I:%M%p'
).replace(tzinfo=_PDT)
_season_2_start = datetime.datetime.strptime(
    'Jul 2 2019 10:00AM',
    '%b %d %Y %I:%M%p'
).replace(tzinfo=_PDT)

SEASONS = {
    0: Season(0, 0, _season_1_start.timestamp()),
    1: Season(1, _season_1_start.timestamp(), _season_2_start.timestamp()),
    2: Season(2, _season_2_start.timestamp(), 1569956446, has_ranked=True),
    3: Season(3, 1569956446, 1569956446 + 4 * 30 * 24 * 60 * 60, has_ranked=True),

    1002: Season(1002, 1565697600, _season_2_start.timestamp() + 9072000_00, season_name='Season 2 Solos'),
}


