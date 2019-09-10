from apextrack.lib.opengraph import Meta

CDN_URL = 'https://d2igtsro72if25.cloudfront.net/2'

WELCOME_META = Meta(
    title='Apex Legends Automatic Match History',
    description='''Automatically track your Apex Legends games with computer vision!
Tracks your rank, placement, kills, downs, route, weapons, and stats.''',
    image_url=f'{CDN_URL}/apex_teaser.png',
    summary_large_image=True,
    oembed=f'{CDN_URL}/oembed.json'
)

