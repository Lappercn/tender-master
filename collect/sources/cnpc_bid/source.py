from collect.domain.source import Channel, Source
from collect.sources.cnpc_bid.constants import CHANNELS, HOME_URL, INTERVAL_MINUTES, SOURCE_ID, SOURCE_NAME

SOURCE = Source(
    id=SOURCE_ID,
    name=SOURCE_NAME,
    home_url=HOME_URL,
    interval_minutes=INTERVAL_MINUTES,
    channels=tuple(Channel(code, name) for code, name in CHANNELS),
    spider="crawl.spiders.cnpc:CnpcSpider",
    net="urban_pipe",
    net_name="城市地下管网",
)
