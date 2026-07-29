from __future__ import annotations

import re
from collections import Counter
from statistics import mean

from app.domain.models import ChannelSnapshot, PostSnapshot
from app.profiling.models import ContentDNAProfile, Evidence, Trait
from app.profiling.normalization import compact_excerpt, normalize_for_llm
from app.profiling.sampling import build_stratified_sample

_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_]+")
_SENTENCE_RE = re.compile(r"[^.!?…]+[.!?…]*")
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF]",
    flags=re.UNICODE,
)
_DIRECT_RE = re.compile(r"\b(?:вы|вам|вас|ваш|ты|тебе|тебя|твой)\b", re.IGNORECASE)
_URL_RE = re.compile(r"(?:https?://|t\.me/|www\.)", re.IGNORECASE)
_PHRASE_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё]{3,}")


def _safe_rate(count: int, base: int) -> float:
    return count / base if base else 0.0


def _evidence(posts: list[PostSnapshot], predicate, limit: int = 3) -> tuple[Evidence, ...]:
    ranked = sorted((p for p in posts if predicate(p)), key=lambda p: p.published_at, reverse=True)
    return tuple(Evidence(p.message_id, compact_excerpt(p.text), p.url) for p in ranked[:limit])


def _trait(
    name: str,
    score: float,
    confidence: float,
    explanation: str,
    evidence: tuple[Evidence, ...],
) -> Trait:
    return Trait(name, round(max(0.0, min(1.0, score)), 3), round(max(0.0, min(1.0, confidence)), 3), explanation, evidence)


def build_content_dna(snapshot: ChannelSnapshot, target_sample_size: int = 180) -> ContentDNAProfile:
    sample = build_stratified_sample(snapshot.posts, target_sample_size)
    posts = [item.post for item in sample]
    texts = [normalize_for_llm(post.text) for post in posts]
    texts = [text for text in texts if text]

    words = [token.lower() for text in texts for token in _WORD_RE.findall(text)]
    unique_words = len(set(words))
    lexical_diversity = _safe_rate(unique_words, len(words))

    sentences = [s.strip() for text in texts for s in _SENTENCE_RE.findall(text) if s.strip()]
    sentence_lengths = [len(_WORD_RE.findall(sentence)) for sentence in sentences if _WORD_RE.findall(sentence)]
    paragraphs = [max(1, len([p for p in text.split("\n\n") if p.strip()])) for text in texts]

    chars = sum(len(text) for text in texts)
    letters = [ch for text in texts for ch in text if ch.isalpha()]
    upper = sum(ch.isupper() for ch in letters)
    emojis = sum(len(_EMOJI_RE.findall(text)) for text in texts)
    questions = sum(text.count("?") for text in texts)
    exclamations = sum(text.count("!") for text in texts)
    ellipses = sum(text.count("...") + text.count("…") for text in texts)
    dashes = sum(text.count("—") + text.count(" – ") for text in texts)
    links = sum(bool(_URL_RE.search(post.text)) for post in posts)
    direct = sum(bool(_DIRECT_RE.search(text)) for text in texts)

    post_count = len(texts)
    uppercase_ratio = _safe_rate(upper, len(letters))
    emoji_rate = _safe_rate(emojis, post_count)
    question_rate = _safe_rate(questions, post_count)
    exclamation_rate = _safe_rate(exclamations, post_count)
    ellipsis_rate = _safe_rate(ellipses, post_count)
    dash_rate = _safe_rate(dashes, post_count)
    link_rate = _safe_rate(links, post_count)
    direct_address_rate = _safe_rate(direct, post_count)

    phrase_counter: Counter[tuple[str, ...]] = Counter()
    for text in texts:
        tokens = [t.lower() for t in _PHRASE_TOKEN_RE.findall(text)]
        phrase_counter.update(zip(tokens, tokens[1:]))
        phrase_counter.update(zip(tokens, tokens[1:], tokens[2:]))
    repeated = tuple(
        (" ".join(phrase), count)
        for phrase, count in phrase_counter.most_common(20)
        if count >= 2
    )[:12]

    markers: list[tuple[str, float]] = [
        ("вопросительная подача", question_rate),
        ("эмоциональная пунктуация", exclamation_rate),
        ("многоточия", ellipsis_rate),
        ("длинное тире", dash_rate),
        ("эмодзи", emoji_rate),
        ("прямое обращение", direct_address_rate),
        ("внешние ссылки", link_rate),
        ("верхний регистр", uppercase_ratio * 10),
    ]
    dominant_markers = tuple(name for name, value in sorted(markers, key=lambda x: x[1], reverse=True)[:5] if value > 0)

    sample_confidence = min(1.0, post_count / 120)
    evidence_confidence = min(1.0, len(snapshot.posts) / 250)
    confidence = round(0.65 * sample_confidence + 0.35 * evidence_confidence, 3)

    mean_sentence = mean(sentence_lengths) if sentence_lengths else 0.0
    mean_paragraphs = mean(paragraphs) if paragraphs else 0.0

    traits = (
        _trait(
            "Формальность",
            min(1.0, 0.45 + mean_sentence / 45 + max(0, link_rate - 0.2) * 0.25 - emoji_rate * 0.05),
            confidence,
            "Оценка основана на длине предложений, частоте ссылок и сдержанности оформления.",
            _evidence(posts, lambda p: len(p.text) >= 800),
        ),
        _trait(
            "Эмоциональность",
            min(1.0, exclamation_rate * 0.22 + emoji_rate * 0.10 + uppercase_ratio * 2.5),
            confidence,
            "Учитываются восклицания, эмодзи и доля верхнего регистра.",
            _evidence(posts, lambda p: "!" in p.text or bool(_EMOJI_RE.search(p.text))),
        ),
        _trait(
            "Диалогичность",
            min(1.0, question_rate * 0.28 + direct_address_rate * 0.65),
            confidence,
            "Учитываются вопросы и прямые обращения к аудитории.",
            _evidence(posts, lambda p: "?" in p.text or bool(_DIRECT_RE.search(p.text))),
        ),
        _trait(
            "Структурированность",
            min(1.0, mean_paragraphs / 6 + dash_rate * 0.06),
            confidence,
            "Оценка основана на абзацной структуре и использовании разделителей.",
            _evidence(posts, lambda p: p.text.count("\n") >= 4),
        ),
        _trait(
            "Ссылочность",
            min(1.0, link_rate),
            confidence,
            "Доля публикаций, содержащих внешние или Telegram-ссылки.",
            _evidence(posts, lambda p: bool(_URL_RE.search(p.text))),
        ),
    )

    limitations = [
        "Профиль описывает публикационный стиль канала, а не личность конкретного автора.",
        "Автопостинг, редакционная команда и шаблоны могут искажать авторские признаки.",
    ]
    if post_count < 60:
        limitations.append("Выборка меньше 60 публикаций: устойчивость части признаков ограничена.")
    if not repeated:
        limitations.append("Недостаточно повторяющихся фраз для устойчивой фразеологической сигнатуры.")

    language_hint = "ru" if sum(bool(re.search(r"[А-Яа-яЁё]", text)) for text in texts) >= post_count / 2 else "other"
    return ContentDNAProfile(
        language_hint=language_hint,
        sample_size=post_count,
        source_post_count=len(snapshot.posts),
        lexical_diversity=round(lexical_diversity, 4),
        mean_sentence_length=round(mean_sentence, 2),
        mean_paragraphs=round(mean_paragraphs, 2),
        uppercase_ratio=round(uppercase_ratio, 4),
        emoji_rate=round(emoji_rate, 4),
        question_rate=round(question_rate, 4),
        exclamation_rate=round(exclamation_rate, 4),
        ellipsis_rate=round(ellipsis_rate, 4),
        dash_rate=round(dash_rate, 4),
        link_rate=round(link_rate, 4),
        direct_address_rate=round(direct_address_rate, 4),
        dominant_markers=dominant_markers,
        repeated_phrases=repeated,
        traits=traits,
        confidence=confidence,
        limitations=tuple(limitations),
    )
