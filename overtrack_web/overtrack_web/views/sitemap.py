import datetime
import logging
from typing import Optional

from dataclasses import dataclass
from flask import Blueprint, url_for, render_template, make_response, Response

from overtrack_models.orm.overwatch_game_summary import OverwatchGameSummary
from overtrack_models.orm.user import User
from overtrack_web.lib.listed_users import get_listed_users

SITEMAP_OVERWATCH_USERS = [
    ('eeveea', 0.75)
]

sitemap_blueprint = Blueprint('sitemap', __name__)
logger = logging.getLogger(__name__)


@dataclass
class SiteMapUrl:
    loc: str
    lastmod: Optional[datetime.datetime] = None
    changefreq: Optional[str] = None
    priority: Optional[float] = None


@sitemap_blueprint.route('/sitemap.xml')
def sitemap():
    urls = [
        SiteMapUrl(
            url_for('root', _external=True),
            priority=1.0,
        ),
        SiteMapUrl(
            url_for('welcome', _external=True),
            priority=1.0,
        ),
        SiteMapUrl(
            url_for('faq', _external=True),
            priority=0.8,
        ),

        SiteMapUrl(
            url_for('client', _external=True),
            priority=0.25,
        ),
        SiteMapUrl(
            url_for('subscribe.subscribe', _external=True),
            priority=0.25,
        ),
    ]

    for username, priority in SITEMAP_OVERWATCH_USERS:
        try:
            user = User.username_index.get(username)
            last_game = OverwatchGameSummary.user_id_time_index.get(user.user_id, scan_index_forward=False)
            urls.append(
                SiteMapUrl(
                    url_for('overwatch.games_list.public_games_list', username='eeveea', _external=True),
                    lastmod=last_game.datetime,
                    changefreq='daily',
                    priority=priority,
                )
            )
        except:
            logger.exception(f'Failed to generate sitemap entry for Overwatch user')

    try:
        for user, last_game, winrates in get_listed_users():
            urls.append(SiteMapUrl(
                url_for('valorant.games_list.public_games_list', username=user.username, _external=True),
                lastmod=last_game.datetime,
                changefreq='daily',
                priority=0.75,
            ))
    except:
        logger.exception(f'Failed to generate sitemap entry for Valorant profiles')

    return render_template(
        'sitemap.xml',
        urls=urls
    )


@sitemap_blueprint.route('/robots.txt')
def robots():
    return Response(
        f'''Sitemap: { url_for('sitemap.sitemap', _external=True) }
    
User-agent: *
Disallow:
        ''',
        mimetype='text/plain',
    )

