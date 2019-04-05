import json
import logging
from itertools import groupby
from typing import List, Dict, Callable, TypeVar, overload

from flask import Blueprint, render_template, jsonify

from api.session import session
from blueprints.login import require_login
from models.apex_game_summary import ApexGameSummary

Data = Dict[str, int]
Group = List[Data]
Bins = List[Group]
T = TypeVar('T')

logger = logging.getLogger(__name__)

results_blueprint = Blueprint('results', __name__)


@results_blueprint.route('/')
@require_login
def results():
    games = [
        {
            'placed': game.placed,
            'kills': game.kills,
            'squad_kills': game.squad_kills
        }
        for game in
        list(ApexGameSummary.user_id_time_index.query(session.user_id))
    ]
    games.sort(key=lambda d: d['placed'])
    bins = [list(group[1]) for group in groupby(games, key=lambda g: g['placed'])]

    placements_data = modify_group(bins, lambda g: len(g))

    total_games = sum(placements_data)
    placements_prob = [
        (sum(placements_data[:i+1]) / total_games) * 100
        for i in range(len(placements_data))
    ]

    kills = sum(g['kills'] for g in games if g['squad_kills'] is not None)
    squad_kills = sum(g['squad_kills'] for g in games if g['squad_kills'] is not None)
    kill_contrib = kills / (squad_kills / 3)

    kills_1 = sum(
        g['kills'] for g in games
        if g['placed'] <= 3 and g['squad_kills'] is not None
    )
    squad_kills_1 = sum(
        g['squad_kills'] for g in games
        if g['placed'] <= 3 and g['squad_kills'] is not None
    )
    kill_contrib_1 = kills_1 / (squad_kills_1 / 3)

    context = {
        'placements_data': json.dumps(placements_data),
        'max_placefreq': max(placements_data),
        'placements_prob': json.dumps(placements_prob),
        'kill_contrib': f'{kill_contrib:.2f}',
        'kill_contrib_1': f'{kill_contrib_1:.2f}',
    }

    return render_template('results.html', **context)


def modify_data(bins: Bins, modifier=Callable[[Data], T]) -> List[List[T]]:
    output_bins = []
    for bin in bins:
        output_bins.append([modifier(d) for d in bin])

    return output_bins


def modify_group(bins: Bins, modifier=Callable[[Group], T]) -> List[T]:
    return [modifier(g) for g in bins]
