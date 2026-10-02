"""Checks that a quote from the LLM really is on the page.

check_quote(quote, page_words, threshold) -> {"verdict": "verified" | "needs_review" | "hallucination", ...}
Critical words (numbers, months, am/pm, before/after/within...) must match exactly.
Other words may differ a little (OCR slips). Low OCR confidence on a mismatch -> needs_review.
"""
import re
from difflib import SequenceMatcher

from rapidfuzz import fuzz

MONTHS = {"january", "february", "march", "april", "may", "june", "july", "august", "september",
          "october", "november", "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug",
          "sep", "sept", "oct", "nov", "dec"}
NUMBER_WORDS = {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
                "fifteen", "twenty", "thirty", "forty", "sixty", "ninety"}
KEY_WORDS = {"am", "pm", "before", "after", "within", "not", "no", "mail", "electronic", "court", "days"}


def normalize(text: str) -> list[str]:
    t = text.lower()
    t = re.sub(r"-\s*\n\s*", "", t)                       # join words split across lines
    t = t.replace("a.m.", "am").replace("p.m.", "pm")
    t = re.sub(r"[‘’“”]", "'", t)
    t = re.sub(r"(?<=\d),(?=\d)", "", t)                  # 25,000 -> 25000
    t = re.sub(r"[^\w\s:$.]|\.(?!\d)", " ", t)            # drop punctuation, keep 8:30 and 2.5
    return t.split()


def is_critical(tok: str) -> bool:
    return any(c.isdigit() for c in tok) or tok in MONTHS | NUMBER_WORDS | KEY_WORDS


def check_quote(quote: str, page_words: list[dict], threshold: float = 80) -> dict:
    tokens, owners = [], []
    for w in page_words:
        for tok in normalize(w["text"]):
            tokens.append(tok)
            owners.append(w)
    q = normalize(quote)
    if not q or not tokens:
        return {"verdict": "hallucination", "reason": "empty quote or page"}

    n, best_i, best = len(q), 0, -1.0
    for i in range(max(1, len(tokens) - n + 1)):
        s = fuzz.ratio(" ".join(q), " ".join(tokens[i:i + n]))
        if s > best:
            best_i, best = i, s
    if best < 70:
        return {"verdict": "hallucination", "reason": "quote not on page", "score": best}

    window = tokens[best_i:best_i + n]
    boxes = [owners[best_i + j]["box"] for j in range(len(window))]
    critical, unclear, soft = [], False, 0
    for op, a1, a2, b1, b2 in SequenceMatcher(None, q, window, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        qa, pb = q[a1:a2], window[b1:b2]
        if any(is_critical(t) for t in qa + pb):
            critical.append({"llm": " ".join(qa), "page": " ".join(pb)})
            unclear |= any(owners[best_i + j]["conf"] < threshold for j in range(b1, b2))
        elif fuzz.ratio(" ".join(qa), " ".join(pb)) < 80:
            soft += 1

    if not critical and soft <= 2:
        return {"verdict": "verified", "score": best, "boxes": boxes}
    if critical and unclear:
        return {"verdict": "needs_review", "reason": "unclear scan", "diffs": critical, "boxes": boxes}
    return {"verdict": "hallucination", "reason": "page says something else",
            "diffs": critical, "soft_diffs": soft, "boxes": boxes}
