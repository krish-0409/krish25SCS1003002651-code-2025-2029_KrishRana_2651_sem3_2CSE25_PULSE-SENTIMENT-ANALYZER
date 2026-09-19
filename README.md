# Pulse — AI Sentiment Analyzer

A full-stack sentiment analysis app for social media posts, customer feedback,
and product reviews. It classifies text as **Positive**, **Negative**, or
**Neutral** with a confidence score, stores results in MongoDB, and shows
them on a dashboard with charts.

**Stack:** Python, Flask, Hugging Face Transformers, PyTorch, MongoDB,
HTML/CSS/JavaScript, Chart.js.

---

## 1. Requirements

- Python 3.9+
- MongoDB running locally (or a connection string to a MongoDB Atlas cluster)
- ~2 GB free disk space for the Transformer model on first run

## 2. Setup

```bash
# 1. Create and activate a virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables
copy .env.example .env      # Windows
cp .env.example .env        # macOS/Linux
# then edit .env if your MongoDB URI is different from the default
```

## 3. Run MongoDB

Make sure MongoDB is running locally on `mongodb://localhost:27017/`
(the default in `.env.example`), or point `MONGO_URI` at your own instance
(e.g. a MongoDB Atlas connection string).

## 4. Run the app

```bash
python app.py
```

The first request that hits the sentiment model will download it from
Hugging Face Hub (`cardiffnlp/twitter-roberta-base-sentiment-latest`,
~500 MB) and cache it locally — this only happens once.

Open **http://localhost:5000** in your browser.

## 5. Using the app

- **Analyze** — paste a single review/post/comment and get an instant
  Positive / Negative / Neutral verdict with a confidence breakdown.
- **Bulk Upload** — upload a `.csv` (first column = text) or `.txt`
  (one entry per line) file, or paste multiple lines directly, to analyze
  up to 500 entries at once.
- **Dashboard** — see total reviews analyzed, the percentage split across
  sentiments, average confidence per class, a pie chart, a bar chart, and a
  paginated, filterable table of everything stored so far.

## 6. REST API

| Method | Endpoint             | Description                                             |
|--------|-----------------------|----------------------------------------------------------|
| GET    | `/api/health`          | Health check                                              |
| POST   | `/api/analyze`         | Body: `{ "text": "..." }` → analyzes and stores one review |
| POST   | `/api/analyze/bulk`    | Body: `{ "texts": ["...", "..."] }` **or** multipart file upload under field `file` (`.csv`/`.txt`) |
| GET    | `/api/results`         | Query params: `page`, `limit`, `sentiment` (`all`/`positive`/`negative`/`neutral`) |
| GET    | `/api/dashboard`       | Aggregate stats: totals, per-class percentages, recent analyses |

Example:

```bash
curl -X POST http://localhost:5000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"text": "This product completely exceeded my expectations!"}'
```

## 7. Project structure

```
sentiment_analyzer/
├── app.py                 # Flask app + REST API routes
├── sentiment_model.py      # Hugging Face Transformer wrapper
├── db.py                   # MongoDB data access layer
├── requirements.txt
├── .env.example
├── templates/
│   └── index.html
└── static/
    ├── css/style.css
    └── js/app.js
```

## 8. Notes

- The model used (`cardiffnlp/twitter-roberta-base-sentiment-latest`) is a
  three-class RoBERTa model trained on ~124M tweets, so it natively returns
  Positive/Negative/Neutral rather than only Positive/Negative.
- To swap in a different Hugging Face model, change `SENTIMENT_MODEL` in
  `.env` — any text-classification model whose labels can be mapped to
  Positive/Negative/Neutral will work.
- All inputs are validated server-side (non-empty, length limits, file type
  checks) and errors are returned as JSON with appropriate HTTP status codes.
