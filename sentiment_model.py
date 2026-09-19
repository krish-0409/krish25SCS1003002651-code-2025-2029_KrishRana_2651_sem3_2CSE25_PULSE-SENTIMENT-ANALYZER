"""
sentiment_model.py
-------------------
Wraps a pre-trained Hugging Face Transformer model to classify text as
Positive, Negative, or Neutral, along with a confidence score.

The model is loaded lazily (on first use) and cached as a module-level
singleton so it is only loaded into memory once per process, regardless
of how many requests come in.
"""

import os
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

# cardiffnlp/twitter-roberta-base-sentiment-latest is a RoBERTa model
# fine-tuned on ~124M tweets and gives three classes out of the box:
# negative, neutral, positive - which maps directly onto this project's needs.
DEFAULT_MODEL_NAME = os.environ.get(
    "SENTIMENT_MODEL", "cardiffnlp/twitter-roberta-base-sentiment-latest"
)

# The model's raw labels (LABEL_0/1/2 or lowercase words depending on
# revision) are normalized to this friendly, display-ready form.
LABEL_MAP = {
    "negative": "Negative",
    "neutral": "Neutral",
    "positive": "Positive",
    "label_0": "Negative",
    "label_1": "Neutral",
    "label_2": "Positive",
}

MAX_INPUT_CHARS = 2000  # guard against pathologically long single inputs


class SentimentModelError(Exception):
    """Raised when the model fails to load or run inference."""


@lru_cache(maxsize=1)
def _get_pipeline():
    """
    Lazily builds and caches the Hugging Face sentiment-analysis pipeline.
    Using lru_cache(maxsize=1) means the (expensive) model load only ever
    happens once per process.
    """
    try:
        from transformers import (
            AutoTokenizer,
            AutoModelForSequenceClassification,
            pipeline,
        )

        tokenizer = AutoTokenizer.from_pretrained(DEFAULT_MODEL_NAME)
        model = AutoModelForSequenceClassification.from_pretrained(DEFAULT_MODEL_NAME)

        return pipeline(
            "sentiment-analysis",
            model=model,
            tokenizer=tokenizer,
            top_k=None,  # return scores for every class, not just the top one
            truncation=True,
        )
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.exception("Failed to load sentiment model")
        raise SentimentModelError(
            f"Could not load sentiment model '{DEFAULT_MODEL_NAME}': {exc}"
        ) from exc


def _normalize_label(raw_label: str) -> str:
    return LABEL_MAP.get(raw_label.strip().lower(), raw_label.title())


def analyze_text(text: str) -> dict:
    """
    Runs sentiment classification on a single piece of text.

    Returns a dict shaped like:
        {
            "sentiment": "Positive" | "Negative" | "Neutral",
            "confidence": 0.9421,                # confidence of the winning class
            "scores": {                           # full probability distribution
                "Positive": 0.9421,
                "Neutral": 0.0421,
                "Negative": 0.0158
            }
        }

    Raises ValueError for invalid input and SentimentModelError if the
    underlying model can't be loaded or run.
    """
    if text is None or not str(text).strip():
        raise ValueError("Text must not be empty.")

    text = str(text).strip()
    if len(text) > MAX_INPUT_CHARS:
        text = text[:MAX_INPUT_CHARS]

    clf = _get_pipeline()

    try:
        raw_result = clf(text)
    except Exception as exc:
        logger.exception("Inference failed")
        raise SentimentModelError(f"Inference failed: {exc}") from exc

    # transformers returns a nested list when top_k=None: [[{...}, {...}, {...}]]
    predictions = raw_result[0] if raw_result and isinstance(raw_result[0], list) else raw_result

    scores = {}
    for pred in predictions:
        label = _normalize_label(pred["label"])
        scores[label] = round(float(pred["score"]), 4)

    # Make sure all three classes are present even if the model omitted one
    for label in ("Positive", "Negative", "Neutral"):
        scores.setdefault(label, 0.0)

    top_label = max(scores, key=scores.get)

    return {
        "sentiment": top_label,
        "confidence": scores[top_label],
        "scores": scores,
    }


def analyze_batch(texts: list) -> list:
    """
    Runs sentiment classification over a list of texts. Invalid/empty
    entries are skipped rather than raising, and a matching list of
    per-item results (or per-item errors) is returned so the caller can
    report partial success on bulk uploads.
    """
    results = []
    for idx, text in enumerate(texts):
        try:
            result = analyze_text(text)
            result["text"] = str(text).strip()
            result["index"] = idx
            result["error"] = None
        except (ValueError, SentimentModelError) as exc:
            result = {
                "index": idx,
                "text": str(text).strip() if text else "",
                "sentiment": None,
                "confidence": None,
                "scores": None,
                "error": str(exc),
            }
        results.append(result)
    return results
