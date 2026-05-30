"""
KWIC (KeyWord In Context) 축약 헬퍼.
외부 공개 화면에서 코퍼스 원문 전체를 노출하지 않기 위해,
검색어(lemma)가 등장한 위치의 좌우 N어절만 잘라 보여준다.
"""

DEFAULT_WINDOW = 20
MAX_CHARS = 250


def make_kwic(content: str, lemma: str, window: int = DEFAULT_WINDOW,
              bold: str = "md") -> str:
    if not content:
        return ""

    text = content.replace("\n", " ").strip()
    tokens = text.split()
    if not tokens:
        return ""

    hit = _find_token_index(tokens, lemma)

    if hit is None:
        left = 0
        right = min(len(tokens), window)
        suffix = "…" if right < len(tokens) else ""
        body = " ".join(tokens[left:right])
        result = f"{body}{suffix}"
    else:
        left = max(0, hit - window)
        right = min(len(tokens), hit + window + 1)
        prefix = "…" if left > 0 else ""
        suffix = "…" if right < len(tokens) else ""
        body = " ".join(tokens[left:right])
        result = f"{prefix}{body}{suffix}"

    return _bold_lemma(_clip_chars(result), lemma, bold)


def _find_token_index(tokens, lemma):
    if not lemma:
        return None
    for i, tok in enumerate(tokens):
        if lemma in tok:
            return i
    stem = lemma[:-1] if lemma.endswith("다") and len(lemma) > 1 else None
    if stem:
        for i, tok in enumerate(tokens):
            if stem in tok:
                return i
    prefix = lemma[:2] if len(lemma) >= 2 else lemma
    if prefix and prefix != stem:
        for i, tok in enumerate(tokens):
            if prefix in tok:
                return i
    return None

def _bold_lemma(text: str, lemma: str, bold: str = "md") -> str:
    if not text or not lemma or bold == "none":
        return text

    def wrap(s):
        return f"**{s}**" if bold == "md" else f"<strong>{s}</strong>"

    if lemma in text:
        return text.replace(lemma, wrap(lemma))
    stem = lemma[:2] if len(lemma) >= 2 else lemma
    if stem and stem in text:
        return text.replace(stem, wrap(stem), 1)
    return text


def _clip_chars(text: str, max_chars: int = MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"
