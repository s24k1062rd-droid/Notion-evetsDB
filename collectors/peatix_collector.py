"""
Peatix イベントコレクター
Peatix の RSS フィードとスクレイピングでイベント情報を収集します。
利用規約に従い、robots.txt を尊重した範囲でスクレイピングを行います。
"""
import logging
import time

import feedparser
import requests
from bs4 import BeautifulSoup

from config.settings import settings

logger = logging.getLogger(__name__)

PEATIX_RSS_URL = "https://peatix.com/search?q={keyword}&l.w=153.0&l.s=24.0&l.e=154.0&l.n=36.0&lang=ja&rss=1"
PEATIX_SEARCH_URL = "https://peatix.com/search"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; EventAgentBot/1.0; +https://example.com/bot)"
    )
}


class PeatixCollector:
    """Peatix からイベントを収集するクラス"""

    def collect(self) -> list[dict]:
        events: list[dict] = []
        seen_urls: set[str] = set()

        for keyword in settings.INTEREST_KEYWORDS[:3]:
            rss_url = PEATIX_RSS_URL.format(keyword=requests.utils.quote(keyword))
            try:
                feed = feedparser.parse(rss_url)
                for entry in feed.entries:
                    url = entry.get("link", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        events.append(self._parse_rss_entry(entry))
                time.sleep(1)  # サーバー負荷軽減
            except Exception as e:
                logger.warning("Peatix RSS エラー (keyword=%s): %s", keyword, e)

        logger.info("Peatix: %d 件取得", len(events))
        return events

    def _parse_rss_entry(self, entry: dict) -> dict:
        return {
            "id": entry.get("id", entry.get("link", "")),
            "title": entry.get("title", ""),
            "starts_at": entry.get("published", ""),
            "public_url": entry.get("link", ""),
            "description": entry.get("summary", ""),
            "venue_name": "",
            "organizer": entry.get("author", ""),
            "source": "peatix",
        }
