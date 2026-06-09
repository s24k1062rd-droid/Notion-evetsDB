"""
Doorkeeper イベントコレクター
Doorkeeper REST API と RSS フィードの両方からイベント情報を収集します。
API仕様: https://www.doorkeeper.jp/developer/api
"""
import logging
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from config.settings import settings

logger = logging.getLogger(__name__)

DOORKEEPER_API_URL = "https://api.doorkeeper.jp/events"
DOORKEEPER_RSS_URL = "https://www.doorkeeper.jp/events.atom"
JST = timezone(timedelta(hours=9))


class DoorkeeperCollector:
    """Doorkeeper からイベントを収集するクラス"""

    def collect(self) -> list[dict]:
        events: list[dict] = []
        events.extend(self._collect_via_api())
        if not events:
            # API 取得失敗時はRSSにフォールバック
            events.extend(self._collect_via_rss())
        # 重複除去（event_id基準）
        seen_ids: set[str] = set()
        unique: list[dict] = []
        for ev in events:
            eid = str(ev.get("id", ev.get("link", "")))
            if eid not in seen_ids:
                seen_ids.add(eid)
                unique.append(ev)
        logger.info("Doorkeeper: %d 件取得（重複除去後）", len(unique))
        return unique

    def _collect_via_api(self) -> list[dict]:
        events: list[dict] = []
        headers: dict[str, str] = {}
        if settings.DOORKEEPER_API_TOKEN:
            headers["Authorization"] = f"Bearer {settings.DOORKEEPER_API_TOKEN}"

        for keyword in settings.INTEREST_KEYWORDS[:5]:  # レート制限対策で最大5キーワード
            params = {"q": keyword, "locale": "ja", "sort": "starts_at"}
            try:
                resp = requests.get(
                    DOORKEEPER_API_URL, params=params, headers=headers, timeout=15
                )
                resp.raise_for_status()
                data = resp.json()
                for item in data:
                    ev = item.get("event", item)
                    events.append(ev)
            except requests.RequestException as e:
                logger.warning("Doorkeeper API エラー (keyword=%s): %s", keyword, e)
                break

        return events

    def _collect_via_rss(self) -> list[dict]:
        """RSS フィードからイベント情報を取得（フォールバック）"""
        events: list[dict] = []
        try:
            feed = feedparser.parse(DOORKEEPER_RSS_URL)
            for entry in feed.entries:
                events.append(
                    {
                        "id": entry.get("id", entry.get("link", "")),
                        "title": entry.get("title", ""),
                        "starts_at": entry.get("published", ""),
                        "public_url": entry.get("link", ""),
                        "description": entry.get("summary", ""),
                        "venue_name": "",
                        "source": "doorkeeper_rss",
                    }
                )
        except Exception as e:
            logger.error("Doorkeeper RSS エラー: %s", e)
        return events
