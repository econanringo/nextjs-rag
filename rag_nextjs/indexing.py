from __future__ import annotations

import re
from collections import Counter

# llms.txt 内の公式ドキュメント URL → nextjs_docs の path 引数
_DOC_PATH = re.compile(r"https://nextjs\.org(/docs[/a-zA-Z0-9._\-]+)")


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9_+\-/]*|[\u3040-\u30ff\u3400-\u9fff]+", text.lower())


def _line_score(query_counter: Counter[str], line: str) -> float:
    line_counter = Counter(tokenize(line))
    if not line_counter:
        return 0.0
    dot = sum(line_counter[w] * query_counter.get(w, 0) for w in line_counter)
    return dot / (sum(line_counter.values()) ** 0.5 + 1e-9)


def extract_doc_paths_from_index(llms_index: str) -> list[tuple[str, str]]:
    """各行について (行テキスト, 最初の /docs パス) を返す。"""
    rows: list[tuple[str, str]] = []
    for line in llms_index.splitlines():
        m = _DOC_PATH.search(line)
        if m:
            rows.append((line, m.group(1)))
    return rows


def rank_doc_paths(query: str, llms_index: str, top_k: int) -> list[str]:
    """クエリとインデックス行の簡易スコアリングで、重複のない path を最大 top_k 件選ぶ。"""
    q = Counter(tokenize(query))
    scored: list[tuple[float, str, str]] = []
    for line, path in extract_doc_paths_from_index(llms_index):
        scored.append((_line_score(q, line), path, line))

    scored.sort(key=lambda x: x[0], reverse=True)
    seen: set[str] = set()
    out: list[str] = []
    for _score, path, _line in scored:
        if path in seen:
            continue
        seen.add(path)
        out.append(path)
        if len(out) >= top_k:
            break
    return out
