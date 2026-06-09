"""
connpass イベントコレクター
connpass API v1 を使用してイベント情報を収集します。
API仕様: https://connpass.com/about/api/
"""
import logging
from datetime import datetime, timedelta, timezone

import requests

from config.settings import settings

logger = logging.getLogger(__name__)

CONNPASS_API_URL = "https://connpass.com/api/v1/event/"
JST = timezone(timedelta(hours=9))


class ConnpassCollector:
    """connpass API からイベントを収集するクラス"""

    def collect(self) -> list[dict]:
        """
        設定キーワードに合致するイベントをAPIから取得します。
        Returns:
            list[dict]: 生のAPIレスポンスイベントリスト
        """
        events: list[dict] = []
        today = datetime.now(JST)
        keyword_str = " ".join(settings.INTEREST_KEYWORDS)

        params = {
            "keyword": keyword_str,
            "count": settings.CONNPASS_COUNT,
            "order": 2,  # 開催日順
            "start_ymd": today.strftime("%Y%m%d"),
            "end_ymd": (today + timedelta(days=settings.COLLECT_DAYS_AHEAD)).strftime("%Y%m%d"),
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        if settings.CONNPASS_API_KEY:
            headers["Authorization"] = f"Bearer {settings.CONNPASS_API_KEY}"

        try:
            resp = requests.get(CONNPASS_API_URL, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            events = data.get("events", [])
            logger.info("connpass: %d 件取得", len(events))
        except requests.RequestException as e:
            logger.error("connpass API エラー: %s", e)

        return events
