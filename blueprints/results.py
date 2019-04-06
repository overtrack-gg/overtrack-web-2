import logging

import numpy as np
from flask import Blueprint, render_template

from api.session import session
from blueprints.login import require_login
from models.apex_game_summary import ApexGameSummary
from overtrack.apex import stats

STAT_FUNCTIONS = {
    'Placement Score': stats.placement_score,
    'Kill Score': stats.kill_score,
    'Squad Kill Contribution': stats.squad_kills_contribution,
    'Average Kills': stats.average_kills,

}


logger = logging.getLogger(__name__)

results_blueprint = Blueprint('results', __name__)


@results_blueprint.route('/')
@require_login
def results():
    games = list(ApexGameSummary.user_id_time_index.query(session.user_id))

    hist, edges = np.histogram([g.placed for g in games], np.linspace(1, 21, 21))
    placements_prob = [
        (np.sum(hist[:i + 1]) / len(games)) * 100
        for i in range(1, 21)
    ]

    statsrow = []
    for name, func in STAT_FUNCTIONS.items():
        statsrow.append((name, *func(games)))

    return render_template(
        'results/results.html',
        placements_data=hist.tolist(),
        placements_prob=placements_prob,

        statsrow=statsrow
    )
