"""
db.py
-----
MongoDB data-access layer for the sentiment analyzer. Keeps all database
concerns (connection, schema shape, queries, aggregations) in one place
so app.py stays focused on HTTP concerns.
"""

import os
import logging
from datetime import datetime, timezone

from pymongo import MongoClient, DESCENDING
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "sentiment_analyzer")

_client = None
_db = None


class DatabaseError(Exception):
    """Raised when a database operation fails."""


def get_db():
    """Lazily creates and caches the MongoDB client/database handle."""
    global _client, _db
    if _db is None:
        try:
            _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            # Force a round trip so connection issues surface immediately
            _client.admin.command("ping")
            _db = _client[MONGO_DB_NAME]
            _db.reviews.create_index([("created_at", DESCENDING)])
            _db.reviews.create_index([("sentiment", 1)])
        except PyMongoError as exc:
            logger.exception("Could not connect to MongoDB")
            raise DatabaseError(f"Could not connect to MongoDB at {MONGO_URI}: {exc}") from exc
    return _db


def insert_review(text: str, sentiment: str, confidence: float, scores: dict, source: str = "single"):
    """Stores one analyzed review and returns its new string id."""
    doc = {
        "text": text,
        "sentiment": sentiment,
        "confidence": confidence,
        "scores": scores,
        "source": source,  # "single" or "bulk"
        "created_at": datetime.now(timezone.utc),
    }
    try:
        result = get_db().reviews.insert_one(doc)
        return str(result.inserted_id)
    except PyMongoError as exc:
        logger.exception("Insert failed")
        raise DatabaseError(f"Could not save review: {exc}") from exc


def insert_many_reviews(items: list):
    """
    Bulk-inserts already-analyzed items. Each item must contain text,
    sentiment, confidence, scores. Returns the number of documents inserted.
    """
    if not items:
        return 0
    docs = [
        {
            "text": item["text"],
            "sentiment": item["sentiment"],
            "confidence": item["confidence"],
            "scores": item["scores"],
            "source": "bulk",
            "created_at": datetime.now(timezone.utc),
        }
        for item in items
        if item.get("sentiment") is not None
    ]
    if not docs:
        return 0
    try:
        result = get_db().reviews.insert_many(docs)
        return len(result.inserted_ids)
    except PyMongoError as exc:
        logger.exception("Bulk insert failed")
        raise DatabaseError(f"Could not save bulk reviews: {exc}") from exc


def _serialize(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    if isinstance(doc.get("created_at"), datetime):
        doc["created_at"] = doc["created_at"].isoformat()
    return doc


def get_results(page: int = 1, limit: int = 20, sentiment: str = None):
    """
    Returns a page of stored reviews, most recent first, optionally
    filtered by sentiment. Returns (items, total_count).
    """
    page = max(1, page)
    limit = max(1, min(limit, 100))
    query = {}
    if sentiment and sentiment.lower() != "all":
        query["sentiment"] = sentiment.capitalize()

    try:
        collection = get_db().reviews
        total = collection.count_documents(query)
        cursor = (
            collection.find(query)
            .sort("created_at", DESCENDING)
            .skip((page - 1) * limit)
            .limit(limit)
        )
        items = [_serialize(doc) for doc in cursor]
        return items, total
    except PyMongoError as exc:
        logger.exception("Query failed")
        raise DatabaseError(f"Could not fetch results: {exc}") from exc


def get_dashboard_stats(recent_limit: int = 8):
    """
    Aggregates overall stats for the dashboard: total review count,
    per-sentiment counts/percentages, average confidence, and the most
    recent analyses.
    """
    try:
        collection = get_db().reviews
        total = collection.count_documents({})

        pipeline = [
            {
                "$group": {
                    "_id": "$sentiment",
                    "count": {"$sum": 1},
                    "avg_confidence": {"$avg": "$confidence"},
                }
            }
        ]
        breakdown = {row["_id"]: row for row in collection.aggregate(pipeline) if row["_id"]}

        sentiments = {}
        for label in ("Positive", "Negative", "Neutral"):
            row = breakdown.get(label, {"count": 0, "avg_confidence": 0})
            count = row["count"]
            sentiments[label] = {
                "count": count,
                "percentage": round((count / total) * 100, 1) if total else 0.0,
                "avg_confidence": round(float(row["avg_confidence"] or 0), 3),
            }

        recent_cursor = collection.find({}).sort("created_at", DESCENDING).limit(recent_limit)
        recent = [_serialize(doc) for doc in recent_cursor]

        return {
            "total_reviews": total,
            "sentiments": sentiments,
            "recent": recent,
        }
    except PyMongoError as exc:
        logger.exception("Dashboard aggregation failed")
        raise DatabaseError(f"Could not compute dashboard stats: {exc}") from exc
