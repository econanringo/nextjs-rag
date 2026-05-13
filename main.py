#!/usr/bin/env python3
"""
Next.js 公式ドキュメント RAG（retrieve: next-devtools-mcp の nextjs_docs）。

次のいずれでも起動できます:
  python main.py "質問"
  python -m rag_nextjs "質問"
  rag-nextjs "質問"   （リポジトリで pip install -e . 後）

使用例:
  python main.py "App Router で Server Actions を使うには？"
  python main.py --top-k 5 "cache components の使い方"

環境変数:
  NVIDIA_API_KEY / OPENAI_API_KEY
  OPENAI_BASE_URL または NVIDIA_OPENAI_BASE_URL（NVIDIA Integrate など）
  CHAT_MODEL（既定: nvidia/nemotron-3-nano-30b-a3b）
  CHAT_STREAM（既定: 1。0 で常に非ストリーミング）
  CHAT_STREAM_FALLBACK（既定: 1。ストリームから本文が得られないとき非ストリームで再試行）
  CHAT_SHOW_REASONING（既定: 0。推論モデルの内部推論を標準出力に出すとき 1）
  CHAT_MAX_TOKENS（任意）
  CHAT_HTTP_TIMEOUT_SECONDS / OPENAI_TIMEOUT / HTTP_TIMEOUT（秒、既定 600）
  CHAT_HTTP_CONNECT_SECONDS（接続タイムアウト秒、既定 30）
  RAG_SPINNER（既定: 1。0 でモデル待ちのアニメーションをオフ／進捗行のみまたは無音）
  RAG_SPINNER_FORCE（既定: 0。TTY でなくてもスピナーを試すとき 1）
  RAG_QUIET（既定: 0。進捗表示をすべて抑止 = --quiet と同種）
  NEXTJS_MCP_COMMAND（既定: npx -y next-devtools-mcp）
  CHAT_EXTRA_BODY（任意: OpenAI クライアントの extra_body に渡す JSON）
"""

from __future__ import annotations

from rag_nextjs.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
