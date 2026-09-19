"""
app.py
------
Flask application entry point for the AI Sentiment Analyzer.

Routes:
    GET  /                      -> serves the single-page web UI
    GET  /api/health            -> basic health check
    POST /api/analyze           -> analyze a single piece of text
    POST /api/analyze/bulk      -> analyze many texts at once (JSON list or file upload)
    GET  /api/results           -> paginated, filterable list of stored analyses
    GET  /api/dashboard         -> aggregate stats for the dashboard view
"""

import os
import io
import csv
import logging

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
from dotenv import load_dotenv

import db
import sentiment_model

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

MAX_BULK_ITEMS = 500
ALLOWED_UPLOAD_EXTENSIONS = {"csv", "txt"}


# ---------------------------------------------------------------------------
# Error handling helpers
# ---------------------------------------------------------------------------

def error_response(message, status_code=400):
    return jsonify({"success": False, "error": message}), status_code


@app.errorhandler(HTTPException)
def handle_http_exception(exc):
    return jsonify({"success": False, "error": exc.description}), exc.code


@app.errorhandler(Exception)
def handle_unexpected_exception(exc):
    logger.exception("Unhandled exception")
    return jsonify({"success": False, "error": "An unexpected server error occurred."}), 500


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.route("/api/health")
def health():
    return jsonify({"success": True, "status": "ok"})


@app.route("/api/analyze", methods=["POST"])
def analyze_single():
    payload = request.get_json(silent=True) or {}
    text = payload.get("text", "")

    if not text or not str(text).strip():
        return error_response("Field 'text' is required and cannot be empty.")

    if len(str(text)) > 10000:
        return error_response("Text is too long. Please limit input to 10,000 characters.")

    try:
        result = sentiment_model.analyze_text(text)
    except ValueError as exc:
        return error_response(str(exc))
    except sentiment_model.SentimentModelError as exc:
        return error_response(str(exc), status_code=503)

    try:
        review_id = db.insert_review(
            text=str(text).strip(),
            sentiment=result["sentiment"],
            confidence=result["confidence"],
            scores=result["scores"],
            source="single",
        )
    except db.DatabaseError as exc:
        # Analysis succeeded even if persistence failed - still return the result,
        # but flag that it wasn't saved so the UI can inform the user.
        return jsonify(
            {
                "success": True,
                "saved": False,
                "warning": f"Result computed but not saved: {exc}",
                "data": result,
            }
        )

    return jsonify({"success": True, "saved": True, "data": {**result, "id": review_id}})


def _extract_texts_from_upload(file_storage):
    filename = file_storage.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise ValueError("Only .csv and .txt files are supported for bulk upload.")

    raw = file_storage.read().decode("utf-8", errors="replace")

    texts = []
    if ext == "csv":
        reader = csv.reader(io.StringIO(raw))
        rows = list(reader)
        if not rows:
            return texts
        # If the first cell of the first row looks like a header (e.g. "text",
        # "review"), skip it; otherwise treat every row's first column as data.
        first_cell = rows[0][0].strip().lower() if rows[0] else ""
        start_idx = 1 if first_cell in ("text", "review", "reviews", "comment", "feedback") else 0
        for row in rows[start_idx:]:
            if row and row[0].strip():
                texts.append(row[0].strip())
    else:  # txt - one review per line
        texts = [line.strip() for line in raw.splitlines() if line.strip()]

    return texts


@app.route("/api/analyze/bulk", methods=["POST"])
def analyze_bulk():
    texts = []

    if "file" in request.files and request.files["file"].filename:
        try:
            texts = _extract_texts_from_upload(request.files["file"])
        except ValueError as exc:
            return error_response(str(exc))
    else:
        payload = request.get_json(silent=True) or {}
        texts = payload.get("texts", [])
        if not isinstance(texts, list):
            return error_response("Field 'texts' must be a list of strings.")

    texts = [t for t in (str(t).strip() for t in texts) if t]

    if not texts:
        return error_response("No valid text entries found to analyze.")

    if len(texts) > MAX_BULK_ITEMS:
        return error_response(f"Too many entries. Limit is {MAX_BULK_ITEMS} per bulk request.")

    try:
        results = sentiment_model.analyze_batch(texts)
    except sentiment_model.SentimentModelError as exc:
        return error_response(str(exc), status_code=503)

    successful = [r for r in results if r["error"] is None]
    failed = [r for r in results if r["error"] is not None]

    saved_count = 0
    try:
        saved_count = db.insert_many_reviews(successful)
    except db.DatabaseError as exc:
        logger.warning("Bulk save failed: %s", exc)

    return jsonify(
        {
            "success": True,
            "summary": {
                "total_submitted": len(texts),
                "analyzed": len(successful),
                "failed": len(failed),
                "saved": saved_count,
            },
            "results": results,
        }
    )


@app.route("/api/results", methods=["GET"])
def get_results():
    try:
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 20))
    except ValueError:
        return error_response("'page' and 'limit' must be integers.")

    sentiment = request.args.get("sentiment")

    try:
        items, total = db.get_results(page=page, limit=limit, sentiment=sentiment)
    except db.DatabaseError as exc:
        return error_response(str(exc), status_code=503)

    return jsonify(
        {
            "success": True,
            "data": items,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": (total + limit - 1) // limit if limit else 0,
            },
        }
    )


@app.route("/api/dashboard", methods=["GET"])
def get_dashboard():
    try:
        stats = db.get_dashboard_stats()
    except db.DatabaseError as exc:
        return error_response(str(exc), status_code=503)

    return jsonify({"success": True, "data": stats})


if __name__ == "__main__":
    port = int(os.environ.get("FLASK_PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "True").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
