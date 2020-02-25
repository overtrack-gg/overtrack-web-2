from dataclasses import dataclass
from flask import Blueprint, render_template_string

from overtrack_web.lib.session import session
from overtrack_web.views.make_discord_bot import create_discord_pages, Checkbox
from overtrack_web.views.overwatch.games_list import get_all_account_names

overwatch_discord_blueprint = Blueprint('overwatch.discord_bot', __name__)


@dataclass
class AccountsList:
    name: str = 'accounts'

    def parse(self, val):
        return val or None

    def render(self) -> str:
        return render_template_string(
            '''
            <div class="col mx-lg-3 p-3 form-group">
                <label for="accountSelector">Accounts:</label>
                <select class="selectpicker form-control"
                        id="accountSelector"
                        name="accounts"
                        data-style="btn-primary btn-block"
                        data-none-selected-text="All Accounts"
                        data-width="100%"
                        multiple>
                    {% for account in account_names %}
                    <option>{{ account }}</option>
                    {% endfor %}
                </select>
            </div>
            ''',
            account_names=get_all_account_names(session.user)
        )


create_discord_pages(
    'overwatch',
    'Overwatch',
    [
        Checkbox('include_quickplay', 'Include Quick Play games', True),
        AccountsList(),
    ],
    overwatch_discord_blueprint
)
