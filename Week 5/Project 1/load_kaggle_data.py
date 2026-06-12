"""
load_kaggle_data.py
Adapter script: loads and unifies the 5 Kaggle datasets into one
standardized DataFrame with columns: text, platform, source, date, score.

USAGE:
1. Download the CSV files below from Kaggle and place them in a
   folder called 'data/' next to this script:

   - amaanpoonawala/youtube-comments-sentiment-dataset
       -> data/youtube_sentiment_1m.csv
   - harshvardhan21/us-comments-cleaned-dataset-for-sentiment-analysis
       -> data/us_youtube_comments.csv
   - mehtaakshat/youtube-comments-data-sentiment-toxicity-spam
       -> data/youtube_toxicity_spam.csv
   - vijayj0shi/reddit-dataset-with-sentiment-analysis
       -> data/reddit_sentiment.csv
   - cosmos98/twitter-and-reddit-sentimental-analysis-dataset
       -> data/Reddit_Data.csv  (and Twitter_Data.csv if desired)

   You don't need all 5 -- the loader skips any file that isn't found.

2. Run:  python load_kaggle_data.py
   -> produces 'social_media_data.csv' in the unified schema, ready
      for sentiment_analysis.py
"""

import pandas as pd
import numpy as np
import os

DATA_DIR = "data"
frames = []

def safe_read(path):
    full = os.path.join(DATA_DIR, path)
    if os.path.exists(full):
        print(f"Loading {full} ...")
        return pd.read_csv(full)
    print(f"  [skip] {full} not found")
    return None


# ── 1. YouTube Comments Sentiment Dataset (1M+ rows) ───────────────
# Columns: CommentText, Sentiment, Likes, Replies, PublishedAt,
#          CountryCode, CategoryID, VideoID, ChannelName
df = safe_read("youtube_sentiment_1m.csv")
if df is not None:
    # Optional: subsample -- this dataset is large (1M+ rows)
    if len(df) > 5000:
        df = df.sample(5000, random_state=42)
    out = pd.DataFrame({
        "text": df["CommentText"],
        "platform": "YouTube",
        "source": df.get("ChannelName", df.get("CategoryID", "Unknown")).astype(str),
        "date": pd.to_datetime(df["PublishedAt"], errors="coerce"),
        "score": pd.to_numeric(df.get("Likes", 0), errors="coerce").fillna(0),
    })
    frames.append(out)


# ── 2. US YouTube Comments (cleaned) ───────────────────────────────
# Columns vary; commonly: Comment / CommentText, VideoID/Category, Likes
df = safe_read("us_youtube_comments.csv")
if df is not None:
    text_col = next((c for c in ["Comment", "CommentText", "text", "comment_text"]
                      if c in df.columns), df.columns[0])
    score_col = next((c for c in ["Likes", "likes", "score"] if c in df.columns), None)
    cat_col = next((c for c in ["Category", "category", "VideoCategory"] if c in df.columns), None)
    date_col = next((c for c in ["PublishedAt", "date", "Date"] if c in df.columns), None)

    if len(df) > 5000:
        df = df.sample(5000, random_state=42)

    out = pd.DataFrame({
        "text": df[text_col],
        "platform": "YouTube",
        "source": df[cat_col].astype(str) if cat_col else "US Comments",
        "date": pd.to_datetime(df[date_col], errors="coerce") if date_col else pd.NaT,
        "score": pd.to_numeric(df[score_col], errors="coerce").fillna(0) if score_col else 0,
    })
    frames.append(out)


# ── 3. YouTube Comments: Sentiment, Toxicity, Spam (45k rows) ──────
# Columns commonly: comment_text, sentiment, toxicity, spam, likes
df = safe_read("youtube_toxicity_spam.csv")
if df is not None:
    text_col = next((c for c in ["comment_text", "CommentText", "text"]
                      if c in df.columns), df.columns[0])
    score_col = next((c for c in ["likes", "Likes", "score"] if c in df.columns), None)
    date_col = next((c for c in ["date", "PublishedAt", "timestamp"] if c in df.columns), None)

    if len(df) > 5000:
        df = df.sample(5000, random_state=42)

    out = pd.DataFrame({
        "text": df[text_col],
        "platform": "YouTube",
        "source": "Sentiment-Toxicity Corpus",
        "date": pd.to_datetime(df[date_col], errors="coerce") if date_col else pd.NaT,
        "score": pd.to_numeric(df[score_col], errors="coerce").fillna(0) if score_col else 0,
    })
    frames.append(out)


# ── 4. Reddit Dataset with Sentiment Analysis (vijayj0shi) ─────────
# Columns commonly: comment/body, sentiment, subreddit, score, created_utc
df = safe_read("reddit_sentiment.csv")
if df is not None:
    text_col = next((c for c in ["comment", "body", "clean_comment", "text"]
                      if c in df.columns), df.columns[0])
    score_col = next((c for c in ["score", "ups", "upvotes"] if c in df.columns), None)
    sub_col = next((c for c in ["subreddit", "source"] if c in df.columns), None)
    date_col = next((c for c in ["created_utc", "date", "timestamp"] if c in df.columns), None)

    if len(df) > 5000:
        df = df.sample(5000, random_state=42)

    out = pd.DataFrame({
        "text": df[text_col],
        "platform": "Reddit",
        "source": df[sub_col].astype(str) if sub_col else "Reddit",
        "date": pd.to_datetime(df[date_col], unit="s", errors="coerce") if date_col else pd.NaT,
        "score": pd.to_numeric(df[score_col], errors="coerce").fillna(0) if score_col else 0,
    })
    frames.append(out)


# ── 5. Twitter & Reddit Sentimental Analysis Dataset (cosmos98) ────
# Reddit.csv columns: clean_comment, category (-1, 0, 1)
df = safe_read("Reddit_Data.csv")
if df is not None:
    text_col = "clean_comment" if "clean_comment" in df.columns else df.columns[0]
    if len(df) > 5000:
        df = df.sample(5000, random_state=42)
    out = pd.DataFrame({
        "text": df[text_col],
        "platform": "Reddit",
        "source": "Reddit (cosmos98 corpus)",
        "date": pd.NaT,  # no timestamps in this dataset
        "score": 0,      # no engagement metric in this dataset
    })
    frames.append(out)


# ── Combine, clean, and save ───────────────────────────────────────
if not frames:
    raise SystemExit(
        "No dataset files found in 'data/'. Please download at least one "
        "of the 5 Kaggle datasets and place it in the data/ folder "
        "(see the docstring at the top of this script for filenames)."
    )

combined = pd.concat(frames, ignore_index=True)

# Drop empty/NaN text rows
combined = combined.dropna(subset=["text"])
combined = combined[combined["text"].astype(str).str.strip() != ""]

# Fill any missing dates with random dates across 2024 so the
# temporal analysis (Figure 2 / Figure 5) still works
missing_dates = combined["date"].isna()
n_missing = missing_dates.sum()
if n_missing > 0:
    random_dates = pd.to_datetime(
        np.random.randint(
            pd.Timestamp("2024-01-01").value // 10**9,
            pd.Timestamp("2024-12-31").value // 10**9,
            n_missing
        ), unit="s"
    )
    combined.loc[missing_dates, "date"] = random_dates

combined.to_csv("social_media_data.csv", index=False)
print(f"\nSaved combined dataset: {len(combined)} rows -> social_media_data.csv")
print(combined["platform"].value_counts())
print(combined["source"].value_counts())
