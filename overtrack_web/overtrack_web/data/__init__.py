import os

from overtrack_web.data import apex_data, overwatch_data
from overtrack_web.data.apex_data import ApexRankSummary, ApexSeason
from overtrack_web.lib.opengraph import Meta

CDN_URL = os.environ.get('CDN_URL', 'https://cdn.overtrack.gg/static')

WELCOME_META = Meta(
    title='Apex Legends Automatic Match History',
    description='''Automatically track your Apex Legends games with computer vision!
Tracks your rank, placement, kills, downs, route, weapons, and stats.''',
    image_url=f'{CDN_URL}/apex_teaser.png',
    summary_large_image=True,
    oembed=f'{CDN_URL}/oembed.json'
)

