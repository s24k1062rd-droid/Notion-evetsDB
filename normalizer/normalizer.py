"""
データ正規化モジュール
各ソースの生データを統一フォーマット（NormalizedEvent）に変換します。

統一フォーマット:
{
    "id":          str   - ソース固有ID
    "source":      str   - データソース名 (connpass / doorkeeper / peatix / prtimes)
    "title":       str   - イベント名
    "description": str   - 説明文
    "start_at":    str   - 開始日時 (ISO 8601 UTC)
    "end_at":      str   - 終了日時 (ISO 8601 UTC) or ""
    "url":         str   - イベントURL
    "venue":       str   - 開催場所
    "organizer":   str   - 主催者
    "tags":        list  - タグリスト
    "capacity":    int   - 定員 (不明な場合は 0)
    "accepted":    int   - 参加登録数 (不明な場合は 0)
    "online":      bool  - オンライン開催フラグ
}
"""
import hashlib
import logging
import re
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class NormalizedEvent:
    id: str = ""
    source: str = ""
    title: str = ""
    description: str = ""
    start_at: str = ""
    end_at: str = ""
    url: str = ""
    venue: str = ""
    organizer: str = ""
    tags: list[str] = field(default_factory=list)
    capacity: int = 0
    accepted: int = 0
    online: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "title": self.title,
            "description": self.description,
            "start_at": self.start_at,
            "end_at": self.end_at,
            "url": self.url,
            "venue": self.venue,
            "organizer": self.organizer,
            "tags": self.tags,
            "capacity": self.capacity,
            "accepted": self.accepted,
            "online": self.online,
        }


class Normalizer:
    """各ソースのデータを NormalizedEvent に変換するクラス"""

    def normalize_all(
        self,
        connpass_events: list[dict],
        doorkeeper_events: list[dict],
        peatix_events: list[dict],
        prtimes_events: list[dict],
    ) -> list[NormalizedEvent]:
        normalized: list[NormalizedEvent] = []
        normalized.extend(self._normalize_connpass(ev) for ev in connpass_events)
        normalized.extend(self._normalize_doorkeeper(ev) for ev in doorkeeper_events)
        normalized.extend(self._normalize_peatix(ev) for ev in peatix_events)
        normalized.extend(self._normalize_prtimes(ev) for ev in prtimes_events)

        # 重複除去（URLベース）
        seen_urls: set[str] = set()
        unique: list[NormalizedEvent] = []
        for ev in normalized:
            if ev.url and ev.url not in seen_urls:
                seen_urls.add(ev.url)
                unique.append(ev)
            elif not ev.url:
                unique.append(ev)

        logger.info("正規化完了: 合計 %d 件（重複除去後）", len(unique))
        return unique

    # ------------------------------------------------------------------
    # connpass
    # ------------------------------------------------------------------
    def _normalize_connpass(self, ev: dict) -> NormalizedEvent:
        venue = ""
        if ev.get("place"):
            venue = ev["place"]
        elif ev.get("address"):
            venue = ev["address"]

        online = self._is_online(ev.get("place", "") + ev.get("address", "") + ev.get("title", ""))

        tags = []
        if ev.get("series") and ev["series"].get("title"):
            tags.append(ev["series"]["title"])

        return NormalizedEvent(
            id=str(ev.get("event_id", "")),
            source="connpass",
            title=ev.get("title", ""),
            description=self._strip_html(ev.get("description", "")),
            start_at=self._to_iso(ev.get("started_at", "")),
            end_at=self._to_iso(ev.get("ended_at", "")),
            url=ev.get("event_url", ""),
            venue=venue,
            organizer=ev.get("owner_display_name", ev.get("owner_nickname", "")),
            tags=tags,
            capacity=int(ev.get("limit", 0) or 0),
            accepted=int(ev.get("accepted", 0) or 0),
            online=online,
        )

    # ------------------------------------------------------------------
    # Doorkeeper
    # ------------------------------------------------------------------
    def _normalize_doorkeeper(self, ev: dict) -> NormalizedEvent:
        source = ev.get("source", "doorkeeper")
        venue_name = ev.get("venue_name") or ""
        address = ev.get("address") or ""
        venue = venue_name or address

        online = self._is_online(venue + ev.get("title", ""))

        return NormalizedEvent(
            id=str(ev.get("id", self._make_id(ev.get("public_url", "")))),
            source=source,
            title=ev.get("title", ""),
            description=self._strip_html(ev.get("description", "")),
            start_at=self._to_iso(ev.get("starts_at", "")),
            end_at=self._to_iso(ev.get("ends_at", "")),
            url=ev.get("public_url", ""),
            venue=venue,
            organizer=ev.get("group_name", ""),
            tags=[],
            capacity=int(ev.get("ticket_limit", 0) or 0),
            accepted=int(ev.get("participants", 0) or 0),
            online=online,
        )

    # ------------------------------------------------------------------
    # Peatix
    # ------------------------------------------------------------------
    def _normalize_peatix(self, ev: dict) -> NormalizedEvent:
        venue = ev.get("venue_name", "")
        online = self._is_online(venue + ev.get("title", ""))
        return NormalizedEvent(
            id=str(ev.get("id", self._make_id(ev.get("public_url", "")))),
            source="peatix",
            title=ev.get("title", ""),
            description=self._strip_html(ev.get("description", "")),
            start_at=self._to_iso(ev.get("starts_at", "")),
            end_at="",
            url=ev.get("public_url", ""),
            venue=venue,
            organizer=ev.get("organizer", ""),
            tags=[],
            capacity=0,
            accepted=0,
            online=online,
        )

    # ------------------------------------------------------------------
    # PR TIMES
    # ------------------------------------------------------------------
    def _normalize_prtimes(self, ev: dict) -> NormalizedEvent:
        return NormalizedEvent(
            id=str(ev.get("id", self._make_id(ev.get("public_url", "")))),
            source="prtimes",
            title=ev.get("title", ""),
            description=self._strip_html(ev.get("description", "")),
            start_at=self._to_iso(ev.get("starts_at", "")),
            end_at="",
            url=ev.get("public_url", ""),
            venue=ev.get("venue_name", ""),
            organizer=ev.get("organizer", ""),
            tags=[],
            capacity=0,
            accepted=0,
            online=False,
        )

    # ------------------------------------------------------------------
    # ユーティリティ
    # ------------------------------------------------------------------
    @staticmethod
    def _to_iso(date_str: str) -> str:
        """様々な日付文字列を ISO 8601 形式に変換する"""
        if not date_str:
            return ""
        try:
            # RFC 2822 形式（RSS で多い）
            dt = parsedate_to_datetime(date_str)
            return dt.isoformat()
        except Exception:
            pass
        # すでに ISO 形式の場合はそのまま返す
        if re.match(r"\d{4}-\d{2}-\d{2}", date_str):
            return date_str
        return date_str

    @staticmethod
    def _strip_html(text: str) -> str:
        """HTMLタグを除去してプレーンテキストに変換する"""
        if not text:
            return ""
        cleaned = re.sub(r"<[^>]+>", "", text)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned[:2000]  # Notion の文字数制限に合わせて切り捨て

    @staticmethod
    def _is_online(text: str) -> bool:
        """オンライン開催かどうかを判定する"""
        online_keywords = ["オンライン", "online", "zoom", "teams", "meet", "webinar", "ウェビナー", "リモート"]
        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in online_keywords)

    @staticmethod
    def _make_id(url: str) -> str:
        """URL から短縮ハッシュIDを生成する"""
        return hashlib.md5(url.encode()).hexdigest()[:12]
