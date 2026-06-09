"""
Notion クライアントモジュール
Notion API を使ってイベントデータベースにページを登録・管理します。

前提: Notion DB に以下のプロパティが存在すること
  - イベント名       (title)
  - 開催日時         (date)
  - URL             (url)
  - ソース           (select)       connpass / doorkeeper / peatix / prtimes
  - 開催形式         (select)       オンライン / オフライン / ハイブリッド
  - 会場             (rich_text)
  - 主催者           (rich_text)
  - AIスコア         (number)
  - AI判定理由       (rich_text)
  - AIタグ           (multi_select)
  - 概要             (rich_text)
  - ステータス        (select)       未確認 / 興味あり / 申し込み済み / 参加済み / 見送り
  - 定員             (number)
  - 参加登録数        (number)
"""
import logging
from typing import Any

from notion_client import Client
from notion_client.errors import APIResponseError

from config.settings import settings
from filter.ai_filter import FilteredEvent

logger = logging.getLogger(__name__)


class NotionClient:
    """Notion DB にイベントを登録するクラス"""

    SOURCE_OPTIONS = {"connpass", "doorkeeper", "peatix", "prtimes", "doorkeeper_rss"}
    DEFAULT_STATUS = "未確認"

    # 必要なプロパティ名とその型のマッピング
    REQUIRED_PROPERTIES: dict[str, str] = {
        "URL": "url",
        "ソース": "select",
        "開催形式": "select",
        "会場": "rich_text",
        "主催者": "rich_text",
        "AIスコア": "number",
        "AI判定理由": "rich_text",
        "概要": "rich_text",
        "定員": "number",
        "参加登録数": "number",
        "AIタグ": "multi_select",
        "開催日時": "date",
    }

    def __init__(self) -> None:
        self._client = Client(auth=settings.NOTION_API_KEY)
        self._db_id = settings.NOTION_DATABASE_ID
        self._setup_database()

    def _setup_database(self) -> None:
        """DBに必要なプロパティが存在することを確認・作成する。型が異なるものは削除して再作成。"""
        try:
            db = self._client.databases.retrieve(database_id=self._db_id)
            existing_props = db.get("properties", {})

            # 型が異なるプロパティを削除
            to_delete: dict[str, Any] = {}
            for name, expected_type in self.REQUIRED_PROPERTIES.items():
                if name in existing_props and existing_props[name].get("type") != expected_type:
                    to_delete[name] = None  # None を指定するとプロパティが削除される

            if to_delete:
                self._client.databases.update(database_id=self._db_id, properties=to_delete)
                logger.info("型不一致プロパティ削除: %s", list(to_delete.keys()))
                db = self._client.databases.retrieve(database_id=self._db_id)
                existing_props = db.get("properties", {})

            # 不足プロパティを追加
            to_add: dict[str, Any] = {}
            for name, expected_type in self.REQUIRED_PROPERTIES.items():
                if name not in existing_props:
                    to_add[name] = {expected_type: {}}

            if to_add:
                self._client.databases.update(database_id=self._db_id, properties=to_add)
                logger.info("DBプロパティ追加: %s", list(to_add.keys()))
                db = self._client.databases.retrieve(database_id=self._db_id)
                existing_props = db.get("properties", {})

            # ステータスプロパティに日本語オプションを追加
            status_options_needed = {"未確認", "興味あり", "申し込み済み", "参加済み", "見送り"}
            current_status_options = {
                opt["name"]
                for opt in existing_props.get("ステータス", {}).get("status", {}).get("options", [])
            }
            if not status_options_needed.issubset(current_status_options):
                merged = list(current_status_options)
                for name in status_options_needed:
                    if name not in current_status_options:
                        merged.append(name)
                try:
                    self._client.databases.update(
                        database_id=self._db_id,
                        properties={"ステータス": {"status": {"options": [{"name": n} for n in merged]}}}
                    )
                    logger.info("ステータスオプション追加完了: %s", status_options_needed - current_status_options)
                except APIResponseError as e:
                    logger.warning("ステータスオプション更新失敗（手動設定が必要）: %s", e)

        except APIResponseError as e:
            logger.warning("DBスキーマ更新失敗（手動でプロパティを設定してください）: %s", e)

    def register_events(self, filtered_events: list[FilteredEvent]) -> tuple[int, int]:
        """
        フィルタリング済みイベントを Notion DB に登録します。
        既に登録済みのイベント（同URLが存在する）はスキップします。

        Returns:
            tuple[int, int]: (登録件数, スキップ件数)
        """
        registered = 0
        skipped = 0

        existing_urls = self._fetch_existing_urls()

        for fe in filtered_events:
            url = fe.event.url
            if url and url in existing_urls:
                logger.debug("スキップ（登録済み）: %s", fe.event.title)
                skipped += 1
                continue
            try:
                self._create_page(fe)
                registered += 1
                logger.info("登録: %s (score=%.2f)", fe.event.title, fe.score)
            except APIResponseError as e:
                logger.error("Notion 登録エラー [%s]: %s", fe.event.title, e)

        logger.info("Notion 登録完了: %d 件登録 / %d 件スキップ", registered, skipped)
        return registered, skipped

    def _fetch_existing_urls(self) -> set[str]:
        """DB に登録済みのURLセットを取得する（重複防止用）"""
        urls: set[str] = set()
        cursor = None
        while True:
            params: dict[str, Any] = {"database_id": self._db_id, "page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            try:
                resp = self._client.databases.query(**params)
            except APIResponseError as e:
                logger.error("Notion DB クエリエラー: %s", e)
                break

            for page in resp.get("results", []):
                props = page.get("properties", {})
                url_prop = props.get("URL", props.get("url", {}))
                url_val = url_prop.get("url", "")
                if url_val:
                    urls.add(url_val)

            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")

        return urls

    def _create_page(self, fe: FilteredEvent) -> None:
        """Notion DB に1ページ（= 1イベント）を作成する"""
        ev = fe.event
        source_name = ev.source.replace("_rss", "")

        # 開催形式の判定
        if ev.online:
            format_option = "オンライン"
        elif ev.venue:
            format_option = "オフライン"
        else:
            format_option = "未定"

        # タグの結合（イベント本来のタグ + AIが提案したタグ）
        all_tags = list(dict.fromkeys(ev.tags + fe.tags_suggested))  # 重複除去・順序保持

        properties: dict[str, Any] = {
            "イベント名": {
                "title": [{"text": {"content": ev.title[:100]}}]
            },
            "URL": {"url": ev.url or None},
            "ソース": {
                "select": {"name": source_name}
            },
            "開催形式": {
                "select": {"name": format_option}
            },
            "会場": {
                "rich_text": [{"text": {"content": ev.venue[:200]}}]
            },
            "主催者": {
                "rich_text": [{"text": {"content": ev.organizer[:200]}}]
            },
            "AIスコア": {"number": round(fe.score, 2)},
            "AI判定理由": {
                "rich_text": [{"text": {"content": fe.reason[:500]}}]
            },
            "概要": {
                "rich_text": [{"text": {"content": ev.description[:1950]}}]
            },
            "ステータス": {
                "status": {"name": self.DEFAULT_STATUS}
            },
            "定員": {"number": ev.capacity or None},
            "参加登録数": {"number": ev.accepted or None},
        }

        # AIタグ
        if all_tags:
            properties["AIタグ"] = {
                "multi_select": [{"name": tag[:100]} for tag in all_tags[:10]]
            }

        # 開催日時
        if ev.start_at:
            date_val: dict[str, Any] = {"start": ev.start_at}
            if ev.end_at:
                date_val["end"] = ev.end_at
            properties["開催日時"] = {"date": date_val}

        self._client.pages.create(
            parent={"database_id": self._db_id},
            properties=properties,
        )
