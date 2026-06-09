"""
Google Cloud Functions エントリーポイント
Cloud Scheduler から HTTP トリガーで呼び出されます。

デプロイコマンド例:
  gcloud functions deploy event-agent \
    --runtime python312 \
    --trigger-http \
    --allow-unauthenticated \
    --entry-point main \
    --region asia-northeast1 \
    --set-env-vars NOTION_API_KEY=...,NOTION_DATABASE_ID=...,OPENAI_API_KEY=...
"""
import json
import logging
import sys

logging.basicConfig(level=logging.INFO, stream=sys.stdout)


def main(request=None):
    """Cloud Functions エントリーポイント（HTTP トリガー）"""
    # リクエストボディから dry_run フラグを取得（省略時は False）
    dry_run = False
    source = "all"
    if request is not None:
        try:
            body = request.get_json(silent=True) or {}
            dry_run = bool(body.get("dry_run", False))
            source = str(body.get("source", "all"))
        except Exception:
            pass

    # main モジュールの run を呼び出す
    import sys
    import os
    # Cloud Functions の場合、ソースコードのルートが sys.path に含まれる
    sys.path.insert(0, os.path.dirname(__file__))

    from main import run
    run(dry_run=dry_run, source=source)

    return json.dumps({"status": "ok"}, ensure_ascii=False), 200, {"Content-Type": "application/json"}


if __name__ == "__main__":
    # ローカルテスト用
    main()
