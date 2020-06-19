from flask import Blueprint

from overtrack_web.views.make_notification_bot import create_notification_pages

valorant_notifications_blueprint = Blueprint('valorant.discord_bot', __name__)


create_notification_pages(
    'valorant',
    'Valorant',
    [
    ],
    valorant_notifications_blueprint,
    twitch_enabled=True,
)
