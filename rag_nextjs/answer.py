from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import stdio_client
from openai import OpenAI

from rag_nextjs.indexing import rank_doc_paths
from rag_nextjs.mcp_docs import (
    fetch_nextjs_docs_page,
    format_fetched_pages,
    next_devtools_stdio_params,
    read_llms_index,
)


def _get_client() -> OpenAI:
    base = os.getenv("OPENAI_BASE_URL") or os.getenv("NVIDIA_OPENAI_BASE_URL")
    key = os.getenv("OPENAI_API_KEY") or os.getenv("NVIDIA_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY または NVIDIA_API_KEY を .env に設定してください")
    kwargs: dict[str, Any] = {"api_key": key}
    if base:
        kwargs["base_url"] = base
    return OpenAI(**kwargs)


def _model_name() -> str:
    return os.getenv("CHAT_MODEL", "nvidia/nemotron-3-nano-30b-a3b")


def _build_messages(question: str, context: str) -> list[dict[str, str]]:
    system = (
        "あなたは Next.js の公式ドキュメント（与えられたコンテキスト）だけを根拠に回答するアシスタントです。"
        "コンテキストに無い内容は推測せず、その旨を述べてください。"
        "コード例は公式に沿った形で示し、必要なら path（ドキュメント上のパス）を引用してください。"
    )
    user = f"## 参照した公式ドキュメント\n\n{context}\n\n## 質問\n\n{question}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


async def gather_context(
    session: ClientSession,
    question: str,
    top_k: int,
) -> tuple[str, list[str]]:
    index = await read_llms_index(session)
    paths = rank_doc_paths(question, index, top_k=top_k)
    if not paths:
        return "", []

    pages: list[dict[str, Any]] = []
    for path in paths:
        try:
            pages.append(await fetch_nextjs_docs_page(session, path))
        except Exception as exc:  # noqa: BLE001
            pages.append({"path": path, "url": "", "content": f"[取得エラー: {exc}]"})

    return format_fetched_pages(pages), paths


def stream_answer(question: str, context: str) -> Iterator[str]:
    client = _get_client()
    model = _model_name()
    messages = _build_messages(question, context)
    extra: dict[str, Any] = {}
    raw_extra = os.getenv("CHAT_EXTRA_BODY")
    if raw_extra:
        import json

        extra = json.loads(raw_extra)

    kwargs_call: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": float(os.getenv("CHAT_TEMPERATURE", "0.2")),
        "stream": True,
    }
    if extra:
        kwargs_call["extra_body"] = extra

    stream = client.chat.completions.create(**kwargs_call)

    for chunk in stream:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        delta = choices[0].delta
        if delta is None:
            continue
        reasoning = getattr(delta, "reasoning_content", None)
        if reasoning:
            yield reasoning
        if delta.content is not None:
            yield delta.content


async def run_rag_cli(question: str, top_k: int) -> None:
    params = next_devtools_stdio_params()

    context = ""
    paths: list[str] = []

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            try:
                await session.call_tool("init", {"project_path": os.getcwd()})
            except Exception:
                pass

            context, paths = await gather_context(session, question, top_k=top_k)

    # MCP 子プロセスを閉じてから LLM ストリーム（空 choices チャンク等の異常時にセッションを巻き込まない）
    if paths:
        print("取得したドキュメント path:", ", ".join(paths))
        print()
    if not context.strip():
        print("関連ドキュメントを取得できませんでした。質問の表現を変えて再度お試しください。")
        return

    for piece in stream_answer(question, context):
        print(piece, end="", flush=True)
    print()
