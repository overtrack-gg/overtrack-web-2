from typing import Optional

from dataclasses import dataclass


@dataclass
class Meta:
    title: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    colour: Optional[str] = None
    summary_large_image: bool = False
    oembed: Optional[str] = None

    twitter_image_url: Optional[str] = None

    def __post_init__(self):
        if not self.twitter_image_url:
            self.twitter_image_url = self.image_url
