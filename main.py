"""
Next.js 公式ドキュメント RAG（retrieve: next-devtools-mcp の nextjs_docs）。

使用例:
  python main.py "App Router で Server Actions を使うには？"
  python main.py --top-k 5 "cache components の使い方"

環境変数:
  NVIDIA_API_KEY / OPENAI_API_KEY
  OPENAI_BASE_URL または NVIDIA_OPENAI_BASE_URL（NVIDIA Integrate など）
  CHAT_MODEL（既定: nvidia/nemotron-3-nano-30b-a3b）
  CHAT_STREAM（既定: 1。0 で常に非ストリーミング）
  CHAT_STREAM_FALLBACK（既定: 1。ストリームから本文が得られないとき非ストリームで再試行）
  CHAT_MAX_TOKENS（任意）
  CHAT_HTTP_TIMEOUT_SECONDS / OPENAI_TIMEOUT / HTTP_TIMEOUT（秒、既定 600）
  CHAT_HTTP_CONNECT_SECONDS（接続タイムアウト秒、既定 30）
  NEXTJS_MCP_COMMAND（既定: npx -y next-devtools-mcp）
  CHAT_EXTRA_BODY（任意: OpenAI クライアントの extra_body に渡す JSON）
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    if not os.getenv("NVIDIA_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        print(
            "エラー: NVIDIA_API_KEY または OPENAI_API_KEY を .env に設定してください。",
            file=sys.stderr,
        )
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Next.js MCP 公式ドキュメント RAG")
    parser.add_argument("question", help="Next.js についての質問")
    parser.add_argument(
        "--top-k",
        type=int,
        default=int(os.getenv("RAG_TOP_K", "4")),
        help="取得するドキュメントページ数（既定 4）",
    )
    args = parser.parse_args()

    from rag_nextjs.answer import run_rag_cli

    asyncio.run(run_rag_cli(args.question, top_k=args.top_k))


if __name__ == "__main__":
    main()
