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
