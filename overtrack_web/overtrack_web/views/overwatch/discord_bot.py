from typing import Optional

from dataclasses import dataclass
from flask import Blueprint, render_template_string, url_for, request, jsonify
from markupsafe import Markup
from werkzeug.utils import redirect

from overtrack_models.orm.game_processed import GameProcessed
from overtrack_models.orm.notifications import DiscordBotNotification
from overtrack_web.lib.authentication import require_login
from overtrack_web.lib.decorators import restrict_origin
from overtrack_web.lib.session import session
from overtrack_web.views.make_notification_bot import create_notification_pages, Checkbox
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


@overwatch_discord_blueprint.route('/delete_webhook', methods=['POST'])
@restrict_origin
@require_login
def delete_webhook():
    to_delete = GameProcessed.get(request.form['id'])
    if to_delete.user_id != session.user_id:
        return "That's not your game D:", 403

    to_delete.delete()
    return redirect(url_for('overwatch.discord_bot.root'))


def legacy_webhooks() -> Optional[Markup]:
    return Markup(
        render_template_string(
            '''
<form action="{{ delete_webhook }}" method="post" class="shadow p-3 rounded">
    <h5 class="card-subtitle mb-2 text-muted">Legacy Webhooks</h5>
    <ul class="list-group discord-notifications">
        {% for webhook in webhooks %}
        <li class="list-group-item" style="line-height: 20pt; max-width: unset; height: 55px;">
            <span class="webhook-url" style="font-size: 10pt !important;">{{ webhook.event_data['webhook'] }}</span>
            <button type="submit" class="btn btn-danger float-right delete-button" name="id" value="{{ webhook.id }}">x</button>
        </li>
        {% endfor %}
    </ul>
</form>
            ''',
            delete_webhook=url_for('overwatch.discord_bot.delete_webhook'),
            webhooks=GameProcessed.user_id_index.query(
                session.user_id,
                GameProcessed.event_type == 'EventType.DISCORD_WEBHOOK',
            )
        )
    )


create_notification_pages(
    'overwatch',
    'Overwatch',
    [
        Checkbox('include_quickplay', 'Include Quick Play games', True),
        AccountsList(),
    ],
    overwatch_discord_blueprint,

    legacy_webhooks,
)

@overwatch_discord_blueprint.route('/data')
@require_login
def data():
    return jsonify([
        b.asdict()
        for b in DiscordBotNotification.user_id_index.query(session.user_id)
    ])



