import logging
from typing import Dict, Any, Optional

from flask import Blueprint, render_template

from overtrack_models.orm.user import User
from overtrack_web.data import WELCOME_META
from overtrack_web.lib import FlaskResponse
from overtrack_web.lib.authentication import check_authentication
from overtrack_web.lib.queries.valorant import get_winrates, get_average_winrates
from overtrack_web.lib.session import session
from overtrack_web.views.valorant.games_list import resolve_public_user

logger = logging.getLogger(__name__)
stats_blueprint = Blueprint('valorant.stats', __name__)


@stats_blueprint.route('')
def winrates() -> FlaskResponse:
    if check_authentication() is None:
        user = session.user
    else:
        user = None
    return render_winrates(user)


@stats_blueprint.route('/<string:username>')
def public_winrates(username: str) -> FlaskResponse:
    if username == 'all':
        return render_winrates(None)
    user = resolve_public_user(username)
    if not user:
        return 'User does not exist or games not public', 404
    return render_winrates(user, public=True)


def render_winrates(user: Optional[User], public: bool = False) -> FlaskResponse:
    average_winrates = get_average_winrates()
    if user is not None:
        has_user = True
        user.refresh()

        target = get_winrates(user.user_id)

        if not user.valorant_games or len(target.maps_agents) == 0:
            logger.info(f'User {user.username} has no games')
            if not public:
                return render_template('client.html', no_games_alert=True, meta=WELCOME_META)

        title = user.username.title() + '\'s Valorant Winrates'
    else:
        has_user = False
        target = average_winrates
        title = 'Average Valorant Winrates'

    maps_list, agents_list = zip(*target.maps_agents.keys())
    maps = set(maps_list)
    agents = set(agents_list)
    maps.remove(None)
    agents.remove(None)
    keys = list(target.maps_agents.keys())

    return render_template(
        'valorant/stats/stats.html',
        title=title,
        has_user=has_user,
        maps=list(maps),
        agents=list(agents),
        keys=keys,
        winrates=target,
        winrates_average=average_winrates,
    )


@stats_blueprint.context_processor
def context_processor() -> Dict[str, Any]:
    return {
        'game_name': 'valorant',
    }


@stats_blueprint.app_template_filter('nround')
def nround(v: Optional[float], digits=0) -> float:
    if v is None:
        return 0
    else:
        return round(v, digits)
