import os

from overtrack_web.data import apex_data, overwatch_data
from overtrack_web.data.apex_data import ApexRankSummary, ApexSeason
from overtrack_web.lib.opengraph import Meta

CDN_URL = os.environ.get('CDN_URL', 'https://cdn.overtrack.gg/static')

WELCOME_META = Meta(
    title='Match History for Overwatch, Valorant, and Apex Legends',
    description=(
        'Automatically track your Overwatch, Valorant, and Apex Legends games with computer vision.\n '
        'Get full match history with details on everything that happened over the course of your games; '
        'kills, deaths, winrate statistics, composition, ults (Overwatch, Valorant), and map route + circles (Apex Legends)'
    ),
    image_url=f'{CDN_URL}/images/teaser.png',
    summary_large_image=True,
    oembed=f'{CDN_URL}/oembed.json'
)

VALORANT_WELCOME_META = Meta(
    title='Match History for Valorant, Overwatch, and Apex Legends',
    description=(
        'Automatically track your Valorant games with computer vision.\n '
        'Get full match history with details on everything that happened over the course of your games; '
        'rounds, kills, deaths, ults, agent/map winrates, and more.'
    ),
    image_url=f'{CDN_URL}/images/valorant_teaser.png',
    summary_large_image=True,
    oembed=f'{CDN_URL}/oembed.json'
)

