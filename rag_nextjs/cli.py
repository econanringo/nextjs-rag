"""
Next.js 公式ドキュメント RAG のエントリポイント（コンソールスクリプト / python -m と共有）。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv


def main() -> int:
    load_dotenv()
    if not os.getenv("NVIDIA_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        print(
            "エラー: NVIDIA_API_KEY または OPENAI_API_KEY を .env に設定してください。",
            file=sys.stderr,
        )
        return 1

    parser = argparse.ArgumentParser(description="Next.js MCP 公式ドキュメント RAG")
    parser.add_argument("question", help="Next.js についての質問")
    parser.add_argument(
        "--top-k",
        type=int,
        default=int(os.getenv("RAG_TOP_K", "4")),
        help="取得するドキュメントページ数（既定 4）",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="進捗・スピナーを出さない（スクリプトからの利用向け）",
    )
    args = parser.parse_args()

    from rag_nextjs.answer import run_rag_cli

    asyncio.run(run_rag_cli(args.question, top_k=args.top_k, quiet=args.quiet))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
