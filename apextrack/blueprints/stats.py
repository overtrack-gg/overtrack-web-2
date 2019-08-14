import logging

import numpy as np
from flask import Blueprint, render_template

from api.authentication import require_authentication
from api.session import session
from apextrack.blueprints.login import require_login
from models.apex_game_summary import ApexGameSummary
from models.user import User
from overtrack.apex import stats

STAT_FUNCTIONS = {
    'Placement Score': stats.placement_score,
    'Kills / 10min': stats.kills_10min,
    'Squad Kill Contribution': stats.squad_kills_contribution,
    'Average Kills': stats.average_kills,

}


logger = logging.getLogger(__name__)

results_blueprint = Blueprint('stats', __name__)

def render_results(user_id: int):
    games = list(ApexGameSummary.user_id_time_index.query(user_id))

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
    return render_results(session.user_id)


@results_blueprint.route('/by_username/<username>')
@require_authentication(superuser_required=True)
def results_by_username(username: str):
    user = User.username_index.get(username)
    return render_results(user.user_id)


@results_blueprint.route('/ashie')
def ashie():
    return ''''<html>
    
    
</html>'''

