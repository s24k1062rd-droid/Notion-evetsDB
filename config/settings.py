"""
設定管理モジュール
.env ファイルから環境変数を読み込み、アプリ全体で共有します。
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Notion
    NOTION_API_KEY: str = os.getenv("NOTION_API_KEY", "")
    NOTION_DATABASE_ID: str = os.getenv("NOTION_DATABASE_ID", "")

    # Gemini
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    # Doorkeeper
    DOORKEEPER_API_TOKEN: str = os.getenv("DOORKEEPER_API_TOKEN", "")

    # connpass
    CONNPASS_API_KEY: str = os.getenv("CONNPASS_API_KEY", "")

    # ユーザーの興味・関心キーワード
    INTEREST_KEYWORDS: list[str] = [
        kw.strip()
        for kw in os.getenv(
            "INTEREST_KEYWORDS",
            "DX,生成AI,AI,LLM,機械学習,Web3,ブロックチェーン,スタートアップ,プロダクト,SaaS",
        ).split(",")
        if kw.strip()
    ]

    # 収集設定
    COLLECT_DAYS_AHEAD: int = int(os.getenv("COLLECT_DAYS_AHEAD", "30"))
    CONNPASS_COUNT: int = int(os.getenv("CONNPASS_COUNT", "100"))
    AI_SCORE_THRESHOLD: float = float(os.getenv("AI_SCORE_THRESHOLD", "0.6"))


settings = Settings()
