import logging
from collections import defaultdict
from pprint import pformat
from typing import DefaultDict, List

from flask import Blueprint, url_for

from overtrack_models.orm.apex_game_summary import ApexGameSummary

logger = logging.getLogger(__name__)

scrims_blueprint = Blueprint('scrims', __name__)


class Match:
    def __init__(self, match_id: str) -> None:
        self.id = match_id
        time, self.champion = match_id.split('/')
        self.raw_time = time
        y, m, d, h, minute = time.split('-')
        self.time = int(minute) + (int(h) * 60) + (int(d) * 60 * 24)

        self.games: DefaultDict[int, List[ApexGameSummary]] = defaultdict(list)

    def add_game(self, g: ApexGameSummary) -> None:
        self.games[g.placed].append(g)

    @property
    def top_game(self) -> ApexGameSummary:
        return self.games[min(self.games)][0]

    def __eq__(self, other) -> bool:
        if isinstance(other, Match):
            return abs(other.time - self.time) <= 2 and other.champion == self.champion
        return False

    def __hash__(self) -> int:
        return hash(self.champion)

    def __str__(self) -> str:
        return pformat(dict(self.games))


@scrims_blueprint.context_processor
def context_processor():
    return {
        'game_name': 'apex'
    }


@scrims_blueprint.route('/directory')
def directory():
    matches = {}
    for g in ApexGameSummary.scrims_match_id_index.query('mendo_duos_beta'):
        match = Match(g.match_id)

        if match not in matches:
            matches[match] = match

        matches[match].add_game(g)

    m_sorted = list(sorted(matches.values(), key=lambda m: m.time, reverse=True))

    html = "<table><thead><tr><th>match link</th><th width=200px>time</th>" \
           "<th>champion</th><th>num teams</th><th>game link</th></tr></thead><tbody>"

    for m in m_sorted:
        g = m.top_game
        key = g.key
        html += '<tr><td><a href="{}">match link</a></td><td>{}</td><td>{}</td>' \
                '<td>{}</td><td>{}</td></tr>'.format(
            url_for('.match_info', time=m.raw_time, champion=m.champion),
            g.time.strftime("%c"),
            m.champion,
            len(m.games),
            f'<a href="/game/{key}">{key}</a>'
        )

    html += "</tbody></table>"

    return html


@scrims_blueprint.route('/match/<time>/<champion>')
def match_info(time: str, champion: str):
    target = Match(f'{time}/{champion}')

    for g in ApexGameSummary.scrims_match_id_index.query('mendo_duos_beta'):
        match = Match(g.match_id)

        if match == target:
            target.add_game(g)

    html = f"For {time}/{champion}" \
           "<table><thead><tr><th>placement</th><th>player</th>" \
           "<th>game link</th></tr></thead><tbody>"

    for placement, games in sorted(target.games.items()):
        for g in games:
            key = g.key
            html += '<tr><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
                placement,
                g.player_name,
                f'<a href="/game/{key}">{key}</a>'
            )

    html += "</tbody></table>"

    return html
