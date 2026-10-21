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

from knowledge.review import normalize_entry

FILLER = re.compile(r"[的了着过在把被一个很好多大小些]")
# Only these documented constructions may normalise non-contiguous words. Never rebuild
# arbitrary nouns from a bag of characters (手机飞到手里 does not contain an aircraft).
NORMALISATIONS = {
    "掉牙": re.compile(
        r"牙(?:齿)?(?:一颗(?:一颗)?|一粒(?:一粒)?|全都|全部|都|又|也|突然|慢慢|不停地|不断地|往下|了|的)*\s*(?:掉|脱落)"
    ),
    "被追": re.compile(
        r"被(?:一[只条个人群]|大|小|陌生的|陌生|凶猛的|凶猛|人|狗|狼|老虎|狮子|怪物|坏人|警察|朋友|同学|追赶者)*追(?:赶)?"
    ),
}


# Heads that end with, or are spelt with, other symbols' aliases but name a different thing:
# 熊猫 is neither a bear nor a cat, 电动车 is not a 动车 train, 雪花 is not a flower. The 2026-10
# review removed them as synonyms (stage1 acceptance, dream-alias-regression.json); without
# this they fell through to containment and were interpreted as the wrong symbol. They stay
# unmatched, and so are never interpreted, until the knowledge base gives them an alias.
DISTINCT_HEADS = ("熊猫", "雪花", "电动车", "鬼压床", "冰山")
# A fragment that drops the object of the alias it belongs to (丢了 is not 钥匙丢了).
BARE_FRAGMENTS = frozenset({"丢了"})


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
            entry = normalize_entry(json.loads(raw))
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
        if query in BARE_FRAGMENTS or any(
            text.endswith(head)
            for text in (query, stripped)
            for head in DISTINCT_HEADS
            if head not in self.aliases
        ):
            return dict(query=query, key=None, method="unmatched", score=0.0)
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

    def spans(self, text: str) -> list[tuple[int, int, str, str]]:
        """Longest non-overlapping alias occurrences: (start, end, alias, key)."""
        taken = [False] * len(text)
        found = []
        # A distinct head is one object: 熊猫 yields neither 熊 nor 猫.
        for head in DISTINCT_HEADS:
            start = -1 if head in self.aliases else text.find(head)
            while start != -1:
                for i in range(start, start + len(head)):
                    taken[i] = True
                start = text.find(head, start + 1)
        for alias in sorted(self.aliases, key=len, reverse=True):
            start = text.find(alias)
            while start != -1:
                span = range(start, start + len(alias))
                if not any(taken[i] for i in span):
                    for i in span:
                        taken[i] = True
                    found.append((start, start + len(alias), alias, self.aliases[alias]))
                start = text.find(alias, start + 1)
        return sorted(found)

    def scan(self, text: str) -> list[str]:
        """Offline baseline extractor (no LLM): keys of the longest alias occurrences.

        Used by the demo route and the offline evaluation; a real model extracts symbols
        itself and passes them, with their source phrases, to lookup_dream_symbols.
        """
        return list(dict.fromkeys(key for _, _, _, key in self.spans(text)))

    def supported(self, phrase: str, symbol: str) -> bool:
        """Whether a symbol is a controlled normalisation of the user's own phrase.

        A known symbol needs a literal alias or an explicitly supported construction
        (牙齿一颗一颗掉下来 → 掉牙, 被一条大狗追 → 被追). Fuzzy retrieval may still
        match the literal supplied symbol, but cannot justify inventing a different one.
        """
        key = self.match(symbol)["key"]
        if key is None:
            return symbol in phrase
        if symbol in phrase or key in self.scan(phrase):
            return True
        rule = NORMALISATIONS.get(key)
        return bool(rule and rule.search(phrase))
