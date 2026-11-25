from collect.domain.source import Channel, Source
from collect.sources.csg_supply.constants import CHANNELS, INTERVAL_MINUTES, ORIGIN, SOURCE_ID, SOURCE_NAME

SOURCE = Source(
    id=SOURCE_ID,
    name=SOURCE_NAME,
    home_url=ORIGIN,
    interval_minutes=INTERVAL_MINUTES,
    channels=tuple(Channel(code, name) for code, name in CHANNELS),
    spider="crawl.spiders.csg:CsgSpider",
)
