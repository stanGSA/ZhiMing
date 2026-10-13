"""Dream symbol matching: synonym table → containment → BM25 candidates + similarity gate.

FTS5 does not segment Chinese, so aliases are indexed as character bigrams (plus single
characters for one-character keys). BM25 only proposes candidates; a candidate is accepted
when the Dice similarity of query and alias bigrams reaches the threshold. Vector retrieval is
not enabled (no embedding model is installed); anything below the threshold is a miss and is
never interpreted.
"""

from __future__ import annotations

import json
import re

FILLER = re.compile(r"[的了着过在把被一个很好多大小些]")


def bigrams(text: str) -> list[str]:
    text = re.sub(r"\s+", "", text)
    return [text[i : i + 2] for i in range(len(text) - 1)] or ([text] if text else [])


def fts_tokens(text: str) -> list[str]:
    return list(dict.fromkeys([*bigrams(text), *text.replace(" ", "")]))


def dice(a: str, b: str) -> float:
    x, y = set(bigrams(a)), set(bigrams(b))
    return 2 * len(x & y) / (len(x) + len(y)) if x and y else 0.0


def containment(query: str, alias: str) -> float:
    """Score for a modifier + known symbol (大狗 → 狗), or a fragment of an alias (牙掉 → 牙掉了).

    The Chinese head noun comes last, so the alias must end the query: 地铁闸机 is about a
    gate, not the metro, and stays unmatched.
    """
    if not query.endswith(alias) and query not in alias:
        return 0.0
    short, long = sorted((len(query), len(alias)))
    return 0.75 + 0.25 * short / long


class DreamMatcher:
    def __init__(self, db, version: str, threshold: float = 0.75):
        self.db, self.version, self.threshold = db, version, threshold
        rows = db.execute(
            "SELECT entry_json FROM entries WHERE system='dream' AND kind='symbol'"
        ).fetchall()
        self.entries = {}
        self.aliases = {}
        for (raw,) in rows:
            entry = json.loads(raw)
            entry["ref_id"] = f"{entry['id']}@{version}"
            self.entries[entry["key"]] = entry
            for alias in (entry["key"], *entry["synonyms"]):
                self.aliases[alias] = entry["key"]

    def match(self, query: str) -> dict:
        query = query.strip()
        if query in self.aliases:
            key = self.aliases[query]
            method = "key" if key == query else "synonym"
            return dict(query=query, key=key, alias=query, method=method, score=1.0)
        stripped = FILLER.sub("", query)
        if stripped and stripped in self.aliases:
            key = self.aliases[stripped]
            return dict(query=query, key=key, alias=stripped, method="synonym", score=1.0)
        best = None
        for alias, key in self.aliases.items():
            score = containment(query, alias)
            # A one-character alias may only explain a short phrase such as 大狗 or 黑猫.
            if score and (len(alias) > 1 or len(query) <= 3):
                candidate = (score, len(alias), alias, key)
                best = max(best, candidate) if best else candidate
        if best and best[0] >= self.threshold:
            return dict(query=query, key=best[3], alias=best[2], method="contains", score=best[0])
        tokens = [t for t in bigrams(query) if '"' not in t]
        if tokens:
            expression = " OR ".join(f'"{t}"' for t in tokens)
            rows = self.db.execute(
                "SELECT alias, bm25(dream_fts) FROM dream_fts WHERE dream_fts MATCH ? "
                "ORDER BY bm25(dream_fts) LIMIT 10",
                (expression,),
            ).fetchall()
            scored = sorted(((dice(query, a), a) for a, _ in rows), reverse=True)
            if scored and scored[0][0] >= self.threshold:
                score, alias = scored[0]
                return dict(
                    query=query, key=self.aliases[alias], alias=alias, method="bm25", score=score
                )
        return dict(query=query, key=None, method="unmatched", score=best[0] if best else 0.0)

    def scan(self, text: str) -> list[str]:
        """Offline baseline extractor (no LLM): longest non-overlapping alias occurrences.

        Used by the demo model and the offline evaluation; a real model extracts symbols
        itself and passes them to lookup_dream_symbols.
        """
        taken = [False] * len(text)
        found = []
        for alias in sorted(self.aliases, key=len, reverse=True):
            start = text.find(alias)
            while start != -1:
                span = range(start, start + len(alias))
                if not any(taken[i] for i in span):
                    for i in span:
                        taken[i] = True
                    key = self.aliases[alias]
                    if key not in found:
                        found.append(key)
                start = text.find(alias, start + 1)
        return found
