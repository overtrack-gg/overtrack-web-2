import logging
from typing import Dict, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


def get_legacy_paths(legacy_base: str) -> Tuple[Dict[str, str], Optional[str]]:
    legacy_scripts = {}
    legacy_stylesheet = None

    logger.info(f'Downloading legacy script paths from {legacy_base}')

    from html.parser import HTMLParser

    class ExtractScripts(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == 'script':
                for name, value in attrs:
                    if name == 'src' and '/' not in value:
                        name = value.split('.', 1)[0]
                        legacy_scripts[name] = value
                        logger.info(f'Got legacy script path: {name}={value!r}')
            if tag == 'link':
                stylesheet = False
                href = None
                for name, value in attrs:
                    if name == 'rel' and value == 'stylesheet':
                        stylesheet = True
                    elif name == 'href' and value.startswith('styles.'):
                        href = value
                if stylesheet and href:
                    nonlocal legacy_stylesheet
                    legacy_stylesheet = href
                    logger.info(f'Got legacy stylesheet path: {legacy_stylesheet!r}')

    r = requests.get(legacy_base)
    r.raise_for_status()
    ExtractScripts().feed(r.text)

    return legacy_scripts, legacy_stylesheet
