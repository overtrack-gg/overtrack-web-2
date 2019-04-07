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
