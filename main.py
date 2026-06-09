"""
イベント管理エージェント メインエントリーポイント
ローカル実行用スクリプト

使用方法:
  python main.py              # 通常実行（全ソース収集・AI判定・Notion登録）
  python main.py --dry-run    # Notion に登録せず結果をコンソール出力のみ
  python main.py --source connpass  # 特定ソースのみ実行
"""
import argparse
import json
import logging
import sys

# ルートロガー設定（ファイル書き出しなし、標準出力のみ）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="イベント管理エージェント")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Notion に登録せず収集・判定結果をコンソールに出力する",
    )
    parser.add_argument(
        "--source",
        choices=["connpass", "doorkeeper", "peatix", "prtimes", "all"],
        default="all",
        help="収集対象ソース（デフォルト: all）",
    )
    parser.add_argument(
        "--output-json",
        metavar="FILE",
        help="フィルタリング結果を JSON ファイルに出力する",
    )
    return parser.parse_args()


def run(dry_run: bool = False, source: str = "all", output_json: str | None = None) -> None:
    from collectors import (
        ConnpassCollector,
        DoorkeeperCollector,
        PeatixCollector,
        PRTimesCollector,
    )
    from normalizer import Normalizer
    from filter import AIFilter
    from notion import NotionClient
    from config.settings import settings

    logger.info("===== イベント管理エージェント 開始 =====")
    logger.info("興味・関心キーワード: %s", ", ".join(settings.INTEREST_KEYWORDS))

    # --- Step 1: 収集 ---
    connpass_events: list[dict] = []
    doorkeeper_events: list[dict] = []
    peatix_events: list[dict] = []
    prtimes_events: list[dict] = []

    if source in ("connpass", "all"):
        logger.info("[1/4] connpass 収集中...")
        connpass_events = ConnpassCollector().collect()

    if source in ("doorkeeper", "all"):
        logger.info("[2/4] Doorkeeper 収集中...")
        doorkeeper_events = DoorkeeperCollector().collect()

    if source in ("peatix", "all"):
        logger.info("[3/4] Peatix 収集中...")
        peatix_events = PeatixCollector().collect()

    if source in ("prtimes", "all"):
        logger.info("[4/4] PR TIMES 収集中...")
        prtimes_events = PRTimesCollector().collect()

    total_collected = len(connpass_events) + len(doorkeeper_events) + len(peatix_events) + len(prtimes_events)
    logger.info("収集合計: %d 件", total_collected)

    if total_collected == 0:
        logger.warning("収集件数が0件です。APIキーや接続設定を確認してください。")
        return

    # --- Step 2: 正規化 ---
    logger.info("データ正規化中...")
    normalizer = Normalizer()
    normalized_events = normalizer.normalize_all(
        connpass_events, doorkeeper_events, peatix_events, prtimes_events
    )

    # --- Step 3: AI フィルタリング ---
    logger.info("AI フィルタリング中... (モデル: %s)", settings.GEMINI_MODEL)
    ai_filter = AIFilter()
    filtered_events = ai_filter.filter(normalized_events)

    logger.info("フィルタリング結果: %d 件が閾値(%.1f)以上", len(filtered_events), settings.AI_SCORE_THRESHOLD)

    # JSON 出力（オプション）
    if output_json:
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump([fe.to_dict() for fe in filtered_events], f, ensure_ascii=False, indent=2)
        logger.info("JSON 出力: %s", output_json)

    if dry_run:
        logger.info("--- DRY RUN: 上位10件のプレビュー ---")
        for i, fe in enumerate(filtered_events[:10], 1):
            print(f"\n[{i}] score={fe.score:.2f} | {fe.event.title}")
            print(f"     ソース: {fe.event.source} | {fe.event.start_at}")
            print(f"     URL: {fe.event.url}")
            print(f"     理由: {fe.reason}")
        return

    # --- Step 4: Notion 登録 ---
    logger.info("Notion DB に登録中...")
    notion = NotionClient()
    registered, skipped = notion.register_events(filtered_events)

    logger.info("===== 完了: %d 件登録 / %d 件スキップ =====", registered, skipped)


if __name__ == "__main__":
    args = parse_args()
    run(dry_run=args.dry_run, source=args.source, output_json=args.output_json)
