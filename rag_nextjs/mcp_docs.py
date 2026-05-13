from __future__ import annotations

import json
import os
import shlex
from typing import Any

from pydantic import AnyUrl

from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client


def next_devtools_stdio_params() -> StdioServerParameters:
    """環境変数 NEXTJS_MCP_COMMAND（既定: npx -y next-devtools-mcp）から起動コマンドを組み立てる。"""
    raw = os.environ.get("NEXTJS_MCP_COMMAND", "npx -y next-devtools-mcp")
    parts = shlex.split(raw)
    if not parts:
        raise ValueError("NEXTJS_MCP_COMMAND が空です")
    return StdioServerParameters(command=parts[0], args=parts[1:])


async def read_llms_index(session: ClientSession) -> str:
    result = await session.read_resource(AnyUrl("nextjs-docs://llms-index"))
    return "".join(c.text or "" for c in result.contents if c.text is not None)


def _tool_text_payload(result: Any) -> str:
    parts: list[str] = []
    for block in getattr(result, "content", ()) or []:
        if getattr(block, "type", None) == "text" and block.text:
            parts.append(block.text)
    return "\n".join(parts)


async def fetch_nextjs_docs_page(session: ClientSession, path: str, anchor: str | None = None) -> dict[str, Any]:
    args: dict[str, Any] = {"path": path}
    if anchor:
        args["anchor"] = anchor
    result = await session.call_tool("nextjs_docs", args)
    if result.isError:
        payload = _tool_text_payload(result)
        raise RuntimeError(f"nextjs_docs 失敗 path={path}: {payload}")

    payload = _tool_text_payload(result)
    data = json.loads(payload)
    return data


def format_fetched_pages(pages: list[dict[str, Any]], max_chars: int = 120_000) -> str:
    chunks: list[str] = []
    total = 0
    for p in pages:
        block = (
            f"### path: {p.get('path')}\n"
            f"url: {p.get('url')}\n\n"
            f"{p.get('content', '')}"
        )
        if total + len(block) > max_chars:
            remain = max_chars - total
            if remain > 500:
                chunks.append(block[:remain] + "\n\n[truncated]")
            break
        chunks.append(block)
        total += len(block)
    return "\n\n---\n\n".join(chunks)


def next_devtools_client():
    """stdio で next-devtools-mcp 子プロセスを起動する `stdio_client` 用コンテキストマネージャ。"""
    return stdio_client(next_devtools_stdio_params())
