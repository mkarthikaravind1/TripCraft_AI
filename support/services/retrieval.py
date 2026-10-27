"""
Lightweight FAQ retrieval: token overlap weighted by inverse document frequency.

Each FAQ's question, keywords and answer are tokenised (lower-case, stop words
removed, light suffix stemming). A query scores against each FAQ by summing
the IDF of shared tokens, with question/keyword matches counting double.
This is small, explainable and reliable for a few dozen FAQs — no vector
database is needed.
"""

import math
import re
from dataclasses import dataclass

from support.models import FAQ

STOP_WORDS = set(
    """a an and are as at be but by can could do does did for from get got have how i if in into is it its
    me my of on or our please so that the their them then there these this to us was we what when where which
    who why will with would you your tripcraft ai i'm im it's dont don't any some just""".split()
)
TOKEN_RE = re.compile(r"[a-z0-9_]+")
MIN_SCORE = 2.2


def stem(word):
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def tokenize(text):
    return [stem(t) for t in TOKEN_RE.findall((text or "").lower()) if t not in STOP_WORDS and len(t) > 1]


@dataclass
class Match:
    faq: FAQ
    score: float


def search(query, limit=3, faqs=None, min_score=MIN_SCORE):
    """Return the most relevant active FAQs for a query, best first."""
    faqs = list(faqs if faqs is not None else FAQ.objects.filter(is_active=True))
    query_tokens = set(tokenize(query))
    if not faqs or not query_tokens:
        return []

    documents = []
    for faq in faqs:
        strong = set(tokenize(faq.question + " " + faq.keywords))
        weak = set(tokenize(faq.answer))
        documents.append((faq, strong, weak))

    total = len(documents)
    def idf(token):
        containing = sum(1 for _, strong, weak in documents if token in strong or token in weak)
        return math.log(1 + total / (1 + containing))

    matches = []
    for faq, strong, weak in documents:
        score = 0.0
        for token in query_tokens:
            if token in strong:
                score += 2 * idf(token)
            elif token in weak:
                score += idf(token)
        # Normalise a little so very long queries don't win on volume alone.
        score = score / math.sqrt(max(len(query_tokens), 1)) * 1.6
        if score >= min_score:
            matches.append(Match(faq=faq, score=round(score, 2)))
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches[:limit]
