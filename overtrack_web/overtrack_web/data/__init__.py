import os

from overtrack_web.data import apex_data, overwatch_data
from overtrack_web.data.apex_data import ApexRankSummary, ApexSeason
from overtrack_web.lib.opengraph import Meta

CDN_URL = os.environ.get('CDN_URL', 'https://cdn.overtrack.gg/static')

WELCOME_META = Meta(
    title='Match History for Overwatch and Apex Legends',
    description=(
        'Automatically track your Overwatch and Apex Legends games with computer vision.\n '
        'Get full match history with details on everything that happened over the course of your games; '
        'kills, deaths, statistics, composition, map route & circles (Apex Legends), ults (Overwatch).\n '
        'Keep track of your overall stats and winrates and watch your progress.'
    ),
    image_url=f'{CDN_URL}/images/teaser.png',
    summary_large_image=True,
    oembed=f'{CDN_URL}/oembed.json'
)

