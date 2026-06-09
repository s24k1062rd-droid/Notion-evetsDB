"""
AI フィルタリングモジュール
Gemini API を使用して、ユーザーの興味・関心に基づいてイベントをスコアリングします。

判定基準:
- 0.0 〜 1.0 のスコアを付与
- 設定した閾値以上のスコアのイベントのみ Notion に登録
"""
import json
import logging
import time
from dataclasses import dataclass

from google import genai
from google.genai import types

from config.settings import settings
from normalizer.normalizer import NormalizedEvent

logger = logging.getLogger(__name__)


@dataclass
class FilteredEvent:
    event: NormalizedEvent
    score: float
    reason: str
    tags_suggested: list[str]

    def to_dict(self) -> dict:
        d = self.event.to_dict()
        d["ai_score"] = self.score
        d["ai_reason"] = self.reason
        d["ai_tags"] = self.tags_suggested
        return d


class AIFilter:
    """Gemini API を使ってイベントの関連度をスコアリングするクラス"""

    def __init__(self) -> None:
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self._interests = "、".join(settings.INTEREST_KEYWORDS)

    def filter(self, events: list[NormalizedEvent]) -> list[FilteredEvent]:
        """
        イベントリストをフィルタリングし、スコアが閾値以上のものを返す。
        バッチ処理でAPIコールを最小化します。
        """
        results: list[FilteredEvent] = []
        batch_size = 15  # 1回のAPIコールで処理するイベント数（無料枠節約のため増やす）

        for i in range(0, len(events), batch_size):
            batch = events[i : i + batch_size]
            batch_results = self._score_batch(batch)
            results.extend(batch_results)
            if i + batch_size < len(events):
                time.sleep(2)  # レート制限対策

        filtered = [r for r in results if r.score >= settings.AI_SCORE_THRESHOLD]
        logger.info(
            "AIフィルター: %d 件中 %d 件が閾値(%.1f)以上",
            len(events),
            len(filtered),
            settings.AI_SCORE_THRESHOLD,
        )
        return sorted(filtered, key=lambda x: x.score, reverse=True)

    def _call_api_with_retry(self, prompt: str, max_retries: int = 5):
        """429 レート制限時に retry-after 秒待機して1回リトライする"""
        import re
        for attempt in range(max_retries + 1):
            try:
                return self._client.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.2,
                    ),
                )
            except Exception as e:
                err_str = str(e)
                is_rate_limit = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
                is_unavailable = "503" in err_str or "UNAVAILABLE" in err_str
                # 1日クォータ上限の場合はリトライしない（すぐに諦める）
                is_daily_quota = "PerDay" in err_str or "per_day" in err_str.lower()
                if is_daily_quota:
                    logger.error("Gemini 1日クォータ上限に達しました。明日以降に再実行してください: %s", e)
                    raise
                if attempt < max_retries and (is_rate_limit or is_unavailable):
                    if is_rate_limit:
                        m = re.search(r"retry in (\d+(?:\.\d+)?)s", err_str)
                        wait = float(m.group(1)) + 2 if m else 62
                        logger.warning("Gemini レート制限 429 - %.0f 秒待機してリトライします", wait)
                    else:
                        wait = 15
                        logger.warning("Gemini 503 UNAVAILABLE - %.0f 秒待機してリトライします", wait)
                    time.sleep(wait)
                else:
                    raise

    def _score_batch(self, events: list[NormalizedEvent]) -> list[FilteredEvent]:
        """複数イベントを一括でスコアリングする"""
        events_text = "\n\n".join(
            f"[{idx + 1}]\nタイトル: {ev.title}\n説明: {ev.description[:400]}"
            for idx, ev in enumerate(events)
        )

        prompt = f"""あなたはイベント選別AIです。以下のユーザーの興味・関心リストに基づいて、各イベントの関連度スコアを判定してください。

【ユーザーの興味・関心】
{self._interests}

【判定するイベント】
{events_text}

各イベントについて以下のJSON配列形式で回答してください。他の文章は一切不要です。
[
  {{
    "index": 1,
    "score": 0.85,
    "reason": "生成AIとLLMに関するハンズオンセミナーで興味関心と高く合致する",
    "tags": ["生成AI", "LLM", "ハンズオン"]
  }},
  ...
]

スコア基準:
- 1.0: 完全に一致（キーワードが複数含まれ、技術的に深い内容）
- 0.8〜0.9: 高い関連性
- 0.6〜0.7: ある程度関連あり
- 0.4〜0.5: 薄い関連性
- 0.0〜0.3: ほぼ無関係"""

        try:
            response = self._call_api_with_retry(prompt)
            content = response.text or "[]"
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                # {"results": [...]} や {"events": [...]} のような形式に対応
                for v in parsed.values():
                    if isinstance(v, list):
                        parsed = v
                        break
                else:
                    parsed = []
        except Exception as e:
            logger.error("Gemini API エラー: %s", e)
            return [FilteredEvent(ev, 0.0, "API エラー", []) for ev in events]

        result_map: dict[int, dict] = {item["index"]: item for item in parsed if isinstance(item, dict)}
        filtered: list[FilteredEvent] = []
        for idx, ev in enumerate(events):
            item = result_map.get(idx + 1, {})
            filtered.append(
                FilteredEvent(
                    event=ev,
                    score=float(item.get("score", 0.0)),
                    reason=str(item.get("reason", "")),
                    tags_suggested=list(item.get("tags", [])),
                )
            )
        return filtered
