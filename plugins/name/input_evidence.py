"""Surname instructions belong to the name they qualify, not the whole conversation."""

import re

SINGLE = re.compile(r"不是复姓|单姓")
ORIGINAL_FORM = re.compile(r"原字|本字|简体|不(?:用|转|写)繁体|就写")


def single_surname(full: str, messages: list[str]) -> bool:
    """Use the latest mention of this full name and its local surname instruction.

    Conjunctions separate people; sentence boundaries separate assertions. A comma before
    the name also stops a preceding person's instruction, while commas in an annotation
    after the name (欧阳明，姓欧，单姓) remain part of that annotation.
    """
    for text in reversed(messages):
        matches = list(re.finditer(re.escape(full), text))
        if not matches:
            continue
        for match in reversed(matches):
            prefix = text[: match.start()]
            # Keep an explicit same-speaker introduction across commas, but not an
            # unrelated person's earlier “单姓” (我姓张，是单姓，看看欧阳子涵).
            introduced = re.search(
                rf"(?:我|本人)姓[“\"「]?{re.escape(full[0])}[”\"」]?[，,\s]*"
                r"(?:是)?单姓[，,\s]*(?:我)?(?:叫|名叫|名字是)[“\"「]?$",
                prefix,
            )
            before = re.split(r"[，,。；;！？!?\n]|和|与|跟", prefix)[-1]
            after = re.split(r"[。；;！？!?\n]|和|与|跟", text[match.end() :])[0]
            local = before + after
            if re.search(r"不是单姓|并非单姓|(?<!不)(?<!不是)(?<!非)复姓", local):
                return False
            if introduced:
                return True
            # A surname stated explicitly is stronger evidence than a generic qualifier.
            if re.search(rf"(?:姓|单姓)(?:是|为)?[“\"「]?{re.escape(full[0])}(?![㐀-鿿])", after):
                return True
            if SINGLE.search(local):
                return True
        return False
    return False
