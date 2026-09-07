from __future__ import annotations


def analyze_content(content_data) -> dict:
    word_count = content_data.word_count or 0
    character_count = content_data.character_count or 0
    paragraph_count = len(content_data.paragraphs or [])
    sentence_count = content_data.sentence_count or 0

    text = content_data.normalized_text or content_data.text or ""
    words = text.split()
    unique_words = len(set(words))

    text_html_ratio = content_data.text_html_ratio or 0.0

    avg_sentence_length = 0.0
    if sentence_count > 0:
        avg_sentence_length = round(word_count / sentence_count, 1)

    avg_paragraph_length = 0.0
    if paragraph_count > 0:
        avg_paragraph_length = round(word_count / paragraph_count, 1)

    return {
        "word_count": word_count,
        "character_count": character_count,
        "unique_word_count": unique_words,
        "sentence_count": sentence_count,
        "paragraph_count": paragraph_count,
        "text_html_ratio": text_html_ratio,
        "avg_sentence_length": avg_sentence_length,
        "avg_paragraph_length": avg_paragraph_length,
    }
