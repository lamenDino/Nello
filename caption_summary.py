"""Small extractive photo summaries: no paid API and no invented facts."""
import re


def summarize_photo(text, limit=450):
    if len(text) <= 600:
        return text
    cleaned = re.sub(r'https?://\S+|(?<!\w)[#@]\w+', '', text)
    candidates = []
    seen = set()
    for part in re.split(r'\n+|(?<=[.!?])\s+', cleaned):
        part = re.sub(r'\s+', ' ', part).strip()
        key = re.sub(r'[^\w€%]', '', part).lower()
        if len(key) < 8 or key in seen:
            continue
        seen.add(key)
        score = 1
        if re.search(r'\d|€|euro|prezzo', part, re.I):
            score += 4
        if re.search(r'esclus|inclus|eccetto|non |senza|obblig|solo |fino al', part, re.I):
            score += 5
        if re.search(r'luned|marted|mercoled|gioved|venerd|sabato|domenica|\bvia\b|piazza|ore |all you can eat', part, re.I):
            score += 4
        # Prefer context near the start when no structured facts are present.
        score += 2 / (1 + len(candidates))
        candidates.append((len(candidates), score, part))
    chosen, used = [], 0
    for index, score, part in sorted(candidates, key=lambda c: -c[1]):
        if used + len(part) + bool(chosen) <= limit and len(chosen) < 5:
            chosen.append((index, part))
            used += len(part) + 1
    if not chosen:
        # A single very long sentence: an explicit excerpt, never a fabricated summary.
        value = re.sub(r'\s+', ' ', cleaned).strip()
        return value[:limit - 1].rsplit(' ', 1)[0].rstrip(' ,;:') + '…'
    return ' '.join(part for _, part in sorted(chosen))
