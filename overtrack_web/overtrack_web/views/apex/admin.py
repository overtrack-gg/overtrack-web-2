from html import escape

import logging

from flask import Blueprint, url_for

from overtrack_models.orm.user import User

logger = logging.getLogger(__name__)

admin = Blueprint('admin', __name__)


@admin.route('/users')
def users():
    return '<ul>\n' + '\n'.join([
        f'<li><a href="{url_for("games_by_key", key=str(u.user_id))}">{escape(u.username)}</a></li>'
        for u in User.apex_games_index.scan()
    ]) + '\n</ul>'


