import logging
import random
from itertools import product
from typing import Dict, Any, Optional, Tuple, List

from dataclasses import dataclass
from flask import Blueprint, render_template

from overtrack_models.dataclasses.valorant import MapName, AgentName
from overtrack_models.orm.user import User
from overtrack_web.data import WELCOME_META
from overtrack_web.lib import FlaskResponse
from overtrack_web.lib.authentication import require_login
from overtrack_web.lib.session import session
from overtrack_web.views.valorant.games_list import resolve_public_user

logger = logging.getLogger(__name__)
stats_blueprint = Blueprint('valorant.stats', __name__)


@stats_blueprint.route('')
@require_login
def games_list() -> FlaskResponse:
    return render_stats(session.user)


@stats_blueprint.route('/<string:username>')
def public_games_list(username: str) -> FlaskResponse:
    user = resolve_public_user(username)
    if not user:
        return 'User does not exist or games not public', 404
    return render_stats(user, public=True)


def render_stats(user: User, public: bool = False) -> FlaskResponse:
    user.refresh()

    if not user.valorant_games:
        logger.info(f'User {user.username} has no games')
        if not public:
            return render_template('client.html', no_games_alert=True, meta=WELCOME_META)

    maps = sorted(['split', 'ascent', 'haven', 'bind'])
    agents = sorted(['raze', 'sova', 'sage', 'breach', 'brimstone', 'cypher', 'jett', 'omen', 'phoenix', 'reyna', 'viper'])

    def random_winrate() -> Winrate:
        return Winrate(random.randint(0, 99), random.randint(0, 99))

    winrates = AllWinrates({
        (m, a): Winrates(random_winrate(), random_winrate(), random_winrate(), random_winrate())
        for m, a in product([None] + maps, [None] + agents)
    })

    winrates_average = AllWinrates({
        (m, a): Winrates(random_winrate(), random_winrate(), random_winrate(), random_winrate())
        for m, a in product([None] + maps, [None] + agents)
    })

    def sort_agents_by_games(agents: List[str]) -> List[str]:
        return ['all agents'] + sorted(agents, key=lambda a: winrates.agent(a).games.winrate, reverse=True)

    return render_template(
        'valorant/stats/stats.html',
        title=user.username.title() + "'s Valorant Stats",
        maps=maps,
        agents=agents,
        winrates=winrates,
        winrates_average=winrates_average,
        sort_agents_by_games=sort_agents_by_games,
        selected_map=None,
        show_averages=True,
        show_detailed=True,
    )


@stats_blueprint.context_processor
def context_processor() -> Dict[str, Any]:
    return {
        'game_name': 'valorant',
    }


# ----- Template Variables -----

# @game_blueprint.app_template_filter('score')
# def score_template_filter(score: Optional[Tuple[int, int]]) -> str:
#     if not score:
#         return '?-?'
#     else:
#         return f'{score[0]}-{score[1]}'


# ----- Template Filters -----

@stats_blueprint.app_template_filter('percentage')
def percentage(frac: Optional[float]) -> str:
    return f'{frac * 100:.0f}%' if frac is not None else '-'

# ----- Utility Functions -----


@dataclass
class Winrate:
    wins: int
    losses: int

    @property
    def total(self):
        return self.wins + self.losses

    @property
    def winrate(self) -> Optional[float]:
        if not self.total:
            return None
        return self.wins / self.total


@dataclass
class Winrates:
    games: Winrate
    rounds: Winrate
    attacking_rounds: Winrate
    defending_rounds: Winrate


@dataclass
class AllWinrates:
    maps_agents: Dict[Tuple[Optional[MapName], Optional[AgentName]], Winrates]

    def map(self, m: MapName) -> Winrates:
        return self.maps_agents[m, None]

    def agent(self, a: AgentName) -> Winrates:
        return self.maps_agents[None, a]

    def map_agent(self, m: MapName, a: AgentName) -> Winrates:
        return self.maps_agents[m, a]

    def all(self) -> Winrates:
        return self.maps_agents[None, None]
