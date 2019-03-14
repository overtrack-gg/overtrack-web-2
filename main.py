import logging

from datetime import datetime
from flask import Flask, render_template, url_for
from flask_bootstrap import Bootstrap
from typing import List, Optional

from overtrack.apex.collect.apex_game import ApexGame
from overtrack.apex.data import Champion
from overtrack.util import s2ts

app = Flask(__name__)
bootstrap = Bootstrap(app)

logger = logging.getLogger(__name__)


def to_ordinal(n: int) -> str:
    suffixes = {1: 'st', 2: 'nd', 3: 'rd'}
    i = n if n < 20 else n % 10
    return f'{n}{suffixes.get(i, "th")}'


def image_url(champ: Optional[Champion]) -> str:
    return url_for('static', filename=f'images/{champ.name.lower()}.png' if champ else 'images/unknown.png')


def strftime(t: float):
    dt = datetime.fromtimestamp(t)
    date = dt.strftime('%c').split(':', 1)[0].rsplit(' ', 1)[0]
    return date + ' ' + dt.strftime('%I:%M %p')


def duration(t: float):
    return s2ts(t).split(':', 1)[1]


@app.route("/")
@app.route("/games")
def games_list():
    context = {
        'games': games,
        'to_ordinal': to_ordinal,
        's2ts': duration,
        'strftime': strftime,
        'image_url': image_url
    }
    return render_template('games.html', **context)


def _load_sample_games() -> List[ApexGame]:
    from overtrack.apex.collect.apex_game_extractor import ApexGameExtractor
    from overtrack.source.video import VideoFrameExtractor
    from overtrack.util import referenced_typedload
    import json
    from overtrack.frame import Frame

    logger.info('Loading frames')
    with open("C:/Users/simon/workspace/overtrack_2/games/apex_eeveea_apex_19-03-13.json") as f:
        frames = referenced_typedload.load(
            json.load(f),
            List[Frame],
            source_type=VideoFrameExtractor.VideoFrameMetadata,
            support_overwatch=False
        )
    logger.info(f'Loaded {len(frames)} frames')

    ex = ApexGameExtractor(keep_games=True)

    for f in frames:
        ex.on_frame(f)
    ex.finish()

    return ex.games


games = _load_sample_games()
