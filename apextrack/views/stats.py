import logging
from typing import List, Tuple

import numpy as np
from flask import Blueprint, render_template

from apextrack.lib.authentication import require_login, require_authentication
from apextrack.lib.session import session
from overtrack_models.apex_game_summary import ApexGameSummary
from overtrack_models.user import User


def _get_points(placed: int) -> int:
    return {
        1: 1000,
        2: 500,
        3: 300,
        4: 100,
        5: 100,
        6: 100,
        7: 50,
        8: 50,
        9: 50,
        10: 50
    }.get(placed, 0)


scoring = np.array([_get_points(i) for i in range(1, 21)])


def placement_score(games: List[ApexGameSummary]) -> Tuple[int, float]:
    placed = np.clip(np.array([g.placed for g in games]), 1, 20)
    scores = scoring[placed - 1]
    return round(float(np.mean(scores)), 1), 1.


def kill_score(games: List[ApexGameSummary]) -> Tuple[int, float]:
    valid_games = [g for g in games if g.placed]
    kills = np.array([g.kills for g in valid_games])
    placed = np.array([g.placed for g in valid_games])
    aggression_scores = kills / ((20 - np.clip(placed, 1, 19)) * 3)
    return round(float(np.mean(aggression_scores) * 1000), 1), len(aggression_scores) / len(games)


def kills_10min(games: List[ApexGameSummary]) -> Tuple[float, float]:
    valid_games = [g for g in games if g.placed]
    kills = np.array([g.kills for g in valid_games])
    durations = np.array([g.duration for g in valid_games])
    return round(float(np.sum(kills) / np.sum(durations / (10 * 60))), 2), len(valid_games) / len(games)


def squad_kills_contribution(games: List[ApexGameSummary]) -> Tuple[float, float]:
    # TODO: if using this count % valid data and warn if low
    valid_games = [g for g in games if g.squad_kills is not None]
    kills = np.array([g.kills for g in valid_games])
    squad_kills = np.array([g.squad_kills for g in valid_games])
    contribution_share = kills / (squad_kills / 3)
    contribution_share[np.isnan(contribution_share)] = 1
    contribution_share = contribution_share[np.isfinite(contribution_share)]
    if len(contribution_share):
        return round(float(np.mean(contribution_share)), 2), len(contribution_share) / len(games)
    else:
        return 0., 0.


def average_kills(games: List[ApexGameSummary]) -> Tuple[float, float]:
    valid_games = [g for g in games if g.placed]
    kills = np.array([g.kills for g in valid_games])
    if len(kills):
        return round(float(np.mean(kills)), 2), len(kills) / len(games)
    else:
        return 0., 0.


def average_squad_kills(games: List[ApexGameSummary]) -> Tuple[float, float]:
    valid_games = [g for g in games if g.placed]
    kills = np.array([g.kills for g in valid_games])
    if len(kills):
        return round(float(np.mean(kills)), 2), len(kills) / len(games)
    else:
        return 0., 0.


STAT_FUNCTIONS = {
    'Placement Score': placement_score,
    'Kills / 10min': kills_10min,
    'Squad Kill Contribution': squad_kills_contribution,
    'Average Kills': average_kills,
}


logger = logging.getLogger(__name__)

results_blueprint = Blueprint('stats', __name__)


def get_games(user: User):
    return list(ApexGameSummary.user_id_time_index.query(user))


def render_results(user: User):
    games = get_games(user)

    if not len(games):
        return render_template('client.html', no_games_alert=True)

    hist, edges = np.histogram([g.placed for g in games], range(1, 22))
    freq = hist / len(games)
    placements_prob = [np.sum(freq[:i]) * 100 for i in range(0, 21)]
    print(freq * 100)
    print(placements_prob)

    statsrow = []
    for name, func in STAT_FUNCTIONS.items():
        statsrow.append((name, *func(games)))

    return render_template(
        'results/results.html',
        placements_data=hist.tolist(),
        placements_prob=placements_prob,

        statsrow=statsrow
    )


@results_blueprint.route('/')
@require_login
def results():
    return render_results(session.user)


@results_blueprint.route('/by_username/<username>')
@require_authentication(superuser_required=True)
def results_by_username(username: str):
    user = User.username_index.get(username)
    return render_results(user)
