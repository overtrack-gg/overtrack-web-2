from flask import Blueprint

from overtrack_web.views.make_discord_bot import create_discord_pages, Checkbox

apex_discord_blueprint = Blueprint('apex.discord_bot', __name__)


create_discord_pages(
    'apex',
    'Apex Legends',
    [
        Checkbox('top3_ony', 'Only post top 3 finishes', False),
    ],
    apex_discord_blueprint,
)
