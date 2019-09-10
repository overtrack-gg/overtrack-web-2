import logging
from collections import defaultdict
from pprint import pprint

from flask import Blueprint, url_for

from overtrack_models.apex_game_summary import ApexGameSummary
from overtrack_models.user import User

logger = logging.getLogger(__name__)

admin = Blueprint('admin', __name__)


@admin.route('/users')
def users():
    return '<ul>\n' + '\n'.join([
        f'<li><a href="{url_for("games_by_key", key=str(u.user_id))}">{u.username}</a></li>'
        for u in User.apex_games_index.scan()
    ]) + '\n</ul>'


