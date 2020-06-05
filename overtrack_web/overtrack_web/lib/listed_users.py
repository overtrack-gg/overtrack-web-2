import logging
from datetime import datetime, timedelta
from functools import lru_cache
from typing import List, Tuple

from overtrack_models.orm.user import User
from overtrack_models.orm.valorant_game_summary import ValorantGameSummary
from overtrack_models.queries.valorant.winrates import MapAgentWinrates

PUBLIC_USERS = [
    'Myth',
    'mendo',
    'Fextralife',
    'ONSCREEN',
    'aceu',
    'FEDMYSTER2',
    'Sykkuno',
    'dizzy',
    'anomaly',
    'dafran',
    'Valkia',
    'Lord_Kebun',
    'Hiko',
]
logger = logging.getLogger(__name__)


@lru_cache()
def get_listed_users() -> List[Tuple[User, ValorantGameSummary, MapAgentWinrates]]:
    logger.info(f'Getting publicly listed Valorant users')

    users = []
    for username in PUBLIC_USERS:
        logger.info(f'Checking {username}')
        try:
            user = User.username_index.get(username)
        except User.DoesNotExist:
            logger.warning(f'  Does not exist')
        else:
            if not user.valorant_games or user.valorant_games < 20:
                logger.info(f'  Has less than 20 games - ignoring')
                continue

            last_valorant_game = ValorantGameSummary.user_id_timestamp_index.get(
                user.user_id,
                scan_index_forward=False,
            )
            if last_valorant_game.datetime < datetime.now() - timedelta(days=7):
                logger.info(f'  Last game is {datetime.now() - last_valorant_game.datetime } ago - ignoring')
                continue

            logger.info(f'  Adding')

            try:
                from overtrack_web.lib.queries.valorant import get_winrates
                wr = get_winrates(user.user_id)
            except:
                logger.exception('Failed to get winrate')
                wr = MapAgentWinrates({})
            users.append((user, last_valorant_game, wr))

    return users
