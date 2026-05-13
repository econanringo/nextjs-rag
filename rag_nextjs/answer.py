from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterator, Mapping
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import stdio_client
from openai import OpenAI

from rag_nextjs.console_status import ConsoleProgress, run_sync_blocking_with_spinner
from rag_nextjs.indexing import rank_doc_paths
from rag_nextjs.mcp_docs import (
    fetch_nextjs_docs_page,
    format_fetched_pages,
    next_devtools_stdio_params,
    read_llms_index,
)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _client_http_timeout() -> Any:
    """HTTP タイムアウト。巨大モデルや遅いゲートウェイ向けに環境変数で延長可能。"""
    import httpx

    raw = (
        os.getenv("OPENAI_TIMEOUT")
        or os.getenv("HTTP_TIMEOUT")
        or os.getenv("CHAT_HTTP_TIMEOUT_SECONDS")
    )
    seconds = float(raw) if raw else 600.0
    connect_raw = os.getenv("CHAT_HTTP_CONNECT_SECONDS")
    connect = float(connect_raw) if connect_raw else 30.0
    return httpx.Timeout(timeout=seconds, connect=connect)


def _get_client() -> OpenAI:
    base = os.getenv("OPENAI_BASE_URL") or os.getenv("NVIDIA_OPENAI_BASE_URL")
    key = os.getenv("OPENAI_API_KEY") or os.getenv("NVIDIA_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY または NVIDIA_API_KEY を .env に設定してください")
    kwargs: dict[str, Any] = {"api_key": key, "timeout": _client_http_timeout()}
    if base:
        kwargs["base_url"] = base
    return OpenAI(**kwargs)


# OpenAI 互換 API が delta に載せる推論テキスト系フィールド（ベンダー差を吸収）
_DELTA_REASONING_KEYS: tuple[str, ...] = (
    "reasoning_content",
    "reasoning",
    "thinking",
    "thought",
)


def _get_str_field(obj: Any, key: str) -> str | None:
    if obj is None:
        return None
    if isinstance(obj, Mapping):
        val = obj.get(key)
    else:
        val = getattr(obj, key, None)
    if isinstance(val, str) and val:
        return val
    return None


def _stringify_content_field(content: Any) -> str | None:
    """message / delta の content が str だけでなく list[dict] 形式のときに連結して返す。"""
    if content is None:
        return None
    if isinstance(content, str):
        return content if content.strip() else None
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str) and block:
                parts.append(block)
                continue
            if isinstance(block, Mapping):
                t = block.get("text")
                if isinstance(t, str) and t:
                    parts.append(t)
                    continue
                if block.get("type") == "text":
                    nested = block.get("text")
                    if isinstance(nested, str) and nested:
                        parts.append(nested)
        return "".join(parts) if parts else None
    return None


def _iter_delta_text_parts(delta: Any) -> Iterator[str]:
    """ストリーミング chunk の delta から、表示すべき文字列を順に取り出す。"""
    if delta is None:
        return
    for key in _DELTA_REASONING_KEYS:
        s = _get_str_field(delta, key)
        if s:
            yield s
    ref = _get_str_field(delta, "refusal")
    if ref:
        yield ref
    raw_c = getattr(delta, "content", None) if not isinstance(delta, Mapping) else delta.get("content")
    c = _stringify_content_field(raw_c)
    if c:
        yield c


def _iter_message_text_parts(message: Any) -> Iterator[str]:
    """非ストリーミング応答の message から表示用テキストを取り出す。"""
    if message is None:
        return
    for key in _DELTA_REASONING_KEYS:
        s = _get_str_field(message, key)
        if s:
            yield s
    ref = _get_str_field(message, "refusal")
    if ref:
        yield ref
    raw_c = getattr(message, "content", None) if not isinstance(message, Mapping) else message.get(
        "content"
    )
    c = _stringify_content_field(raw_c)
    if c:
        yield c


def _iter_chunk_text_parts(chunk: Any) -> Iterator[str]:
    """ChatCompletionChunk 互換オブジェクトからテキスト断片を取り出す。"""
    choices = getattr(chunk, "choices", None) or []
    for choice in choices:
        delta = getattr(choice, "delta", None)
        yield from _iter_delta_text_parts(delta)
        # 一部プロキシはストリーム終端付近で message に本文だけ載せる
        msg = getattr(choice, "message", None)
        yield from _iter_message_text_parts(msg)


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
    *,
    on_phase: Callable[[str, str], None] | None = None,
) -> tuple[str, list[str]]:
    if on_phase:
        on_phase("インデックスを読み込み中", "")
    index = await read_llms_index(session)
    paths = rank_doc_paths(question, index, top_k=top_k)
    if not paths:
        return "", []

    pages: list[dict[str, Any]] = []
    for i, path in enumerate(paths, 1):
        if on_phase:
            on_phase("ドキュメント本文を取得中", f"{i}/{len(paths)}  {path}")
        try:
            pages.append(await fetch_nextjs_docs_page(session, path))
        except Exception as exc:  # noqa: BLE001
            pages.append({"path": path, "url": "", "content": f"[取得エラー: {exc}]"})

    return format_fetched_pages(pages), paths


def _extra_body_from_env() -> dict[str, Any]:
    raw_extra = os.getenv("CHAT_EXTRA_BODY")
    if not raw_extra:
        return {}
    import json

    return json.loads(raw_extra)


def _build_chat_completion_kwargs(question: str, context: str, *, stream: bool) -> dict[str, Any]:
    model = _model_name()
    messages = _build_messages(question, context)
    extra = _extra_body_from_env()

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": float(os.getenv("CHAT_TEMPERATURE", "0.2")),
        "stream": stream,
    }

    mt = os.getenv("CHAT_MAX_TOKENS")
    if mt and mt.strip():
        kwargs["max_tokens"] = int(mt.strip())

    if extra:
        kwargs["extra_body"] = extra

    if stream and _env_bool("CHAT_STREAM_INCLUDE_USAGE", False):
        kwargs["stream_options"] = {"include_usage": True}

    return kwargs


def _non_stream_completion(client: OpenAI, kwargs: dict[str, Any]) -> Iterator[str]:
    kw = dict(kwargs)
    kw["stream"] = False
    kw.pop("stream_options", None)
    resp = client.chat.completions.create(**kw)
    choices = getattr(resp, "choices", None) or []
    if not choices:
        yield "[エラー] API 応答に choices がありません。"
        return
    msg = getattr(choices[0], "message", None)
    parts = list(_iter_message_text_parts(msg))
    if parts:
        for p in parts:
            yield p
        return
    first = choices[0]
    yield (
        "[エラー] メッセージ本文を取得できませんでした。"
        f" finish_reason={getattr(first, 'finish_reason', None)!r}"
    )


def stream_answer(question: str, context: str) -> Iterator[str]:
    """OpenAI Chat Completions 互換エンドポイント向け。ストリーム非対応・空ストリームのモデルは非ストリームにフォールバック。"""
    client = _get_client()
    use_stream = _env_bool("CHAT_STREAM", True)
    fb = _env_bool("CHAT_STREAM_FALLBACK", True)

    if not use_stream:
        kwargs = _build_chat_completion_kwargs(question, context, stream=False)
        yield from _non_stream_completion(client, kwargs)
        return

    kwargs_stream = _build_chat_completion_kwargs(question, context, stream=True)
    stream = client.chat.completions.create(**kwargs_stream)

    got_text = False
    try:
        for chunk in stream:
            for piece in _iter_chunk_text_parts(chunk):
                got_text = True
                yield piece
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()

    if not got_text and fb:
        kwargs_ns = _build_chat_completion_kwargs(question, context, stream=False)
        yield from _non_stream_completion(client, kwargs_ns)


async def run_rag_cli(question: str, top_k: int, *, quiet: bool = False) -> None:
    params = next_devtools_stdio_params()

    quiet = quiet or _env_bool("RAG_QUIET", False)
    progress = ConsoleProgress(enabled=not quiet)

    context = ""
    paths: list[str] = []

    try:
        progress.start("next-devtools-mcp を起動・接続中 …")

        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                progress.phase("next-devtools-mcp と通信中 …", "")
                try:
                    await session.call_tool("init", {"project_path": os.getcwd()})
                except Exception:
                    pass

                context, paths = await gather_context(
                    session,
                    question,
                    top_k,
                    on_phase=lambda main, detail="": progress.phase(main, detail),
                )
    finally:
        progress.stop_clear()

    # MCP 子プロセスを閉じてから LLM ストリーム（空 choices チャンク等の異常時にセッションを巻き込まない）
    if paths:
        print("取得したドキュメント path:", ", ".join(paths))
        print()
    if not context.strip():
        print("関連ドキュメントを取得できませんでした。質問の表現を変えて再度お試しください。")
        return

    iterator = iter(stream_answer(question, context))
    first = run_sync_blocking_with_spinner(
        lambda: next(iterator, None),
        out=sys.stderr,
        main="モデル応答を待機中",
        detail=_model_name(),
        enabled=(not quiet),
    )
    if first is None:
        print()
        return

    sys.stdout.write(first)
    sys.stdout.flush()
    for piece in iterator:
        sys.stdout.write(piece)
        sys.stdout.flush()
    sys.stdout.write("\n")
    sys.stdout.flush()
