"""
PR TIMES イベントコレクター
PR TIMES の RSS フィードからイベント・セミナー関連プレスリリースを収集します。
RSS仕様: https://prtimes.jp/main/html/rss/index.html
"""
import logging

import feedparser

from config.settings import settings

logger = logging.getLogger(__name__)

# キーワード別 RSS URL（PR TIMES はカテゴリ別RSSを提供）
PRTIMES_RSS_URLS = [
    "https://prtimes.jp/rss2.0/new/action.rss",  # 最新プレスリリース
]


class PRTimesCollector:
    """PR TIMES からイベント関連情報を収集するクラス"""

    def collect(self) -> list[dict]:
        events: list[dict] = []
        seen_urls: set[str] = set()

        for rss_url in PRTIMES_RSS_URLS:
            try:
                feed = feedparser.parse(rss_url)
                for entry in feed.entries:
                    url = entry.get("link", "")
                    title = entry.get("title", "")
                    summary = entry.get("summary", "")
                    # イベント・セミナー関連のみ抽出
                    if self._is_event_related(title, summary):
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            events.append(self._parse_entry(entry))
            except Exception as e:
                logger.error("PR TIMES RSS エラー: %s", e)

        logger.info("PR TIMES: %d 件取得", len(events))
        return events

    def _is_event_related(self, title: str, summary: str) -> bool:
        """イベント・セミナー関連かどうかを判定"""
        event_keywords = ["イベント", "セミナー", "ウェビナー", "webinar", "勉強会", "カンファレンス", "conference", "展示会"]
        text = (title + " " + summary).lower()
        return any(kw.lower() in text for kw in event_keywords + settings.INTEREST_KEYWORDS)

    def _parse_entry(self, entry: dict) -> dict:
        return {
            "id": entry.get("id", entry.get("link", "")),
            "title": entry.get("title", ""),
            "starts_at": entry.get("published", ""),
            "public_url": entry.get("link", ""),
            "description": entry.get("summary", ""),
            "venue_name": "",
            "organizer": entry.get("author", ""),
            "source": "prtimes",
        }
