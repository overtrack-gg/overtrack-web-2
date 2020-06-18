from flask import Blueprint

from overtrack_web.views.make_discord_bot import create_discord_pages

valorant_discord_blueprint = Blueprint('valorant.discord_bot', __name__)


create_discord_pages(
    'valorant',
    'Valorant',
    [
    ],
    valorant_discord_blueprint,
)
