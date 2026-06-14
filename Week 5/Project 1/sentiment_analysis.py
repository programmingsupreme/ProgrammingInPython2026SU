"""
Sentiment Analysis of Social Media Discourse
Cross-Platform NLP Study: Reddit and YouTube
CPS 3320 — Python Data Analysis and Machine Learning
Author: Vikram Nadathur
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from textblob import TextBlob
from sklearn.feature_extraction.text import TfidfVectorizer
from scipy import stats
import warnings, re, os
warnings.filterwarnings('ignore')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(SCRIPT_DIR, 'figures'), exist_ok=True)

# ── 1. LOAD DATA ───────────────────────────────────────────
# Replace with actual Kaggle dataset path:
# df = pd.read_csv('your_kaggle_dataset.csv')
# Required columns: text, platform, source, date, score

df = pd.read_csv(os.path.join(SCRIPT_DIR, 'social_media_data.csv'), parse_dates=['date'])
print(f"Loaded {len(df)} records\n")

# ── 2. PREPROCESSING ───────────────────────────────────────
def clean_text(t):
    t = str(t).lower()
    t = re.sub(r'http\S+', '', t)
    t = re.sub(r'[^a-z\s]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

df['clean_text'] = df['text'].apply(clean_text)

# ── 3. SENTIMENT SCORING ───────────────────────────────────
sia = SentimentIntensityAnalyzer()

def vader_scores(text):
    s = sia.polarity_scores(text)
    return pd.Series([s['compound'], s['pos'], s['neg'], s['neu']])

df[['vader_compound','vader_pos','vader_neg','vader_neu']] = df['text'].apply(vader_scores)

def textblob_scores(text):
    tb = TextBlob(text)
    return pd.Series([tb.sentiment.polarity, tb.sentiment.subjectivity])

df[['tb_polarity','tb_subjectivity']] = df['clean_text'].apply(textblob_scores)

def vader_label(c):
    if c >= 0.05:  return 'Positive'
    elif c <= -0.05: return 'Negative'
    return 'Neutral'

df['vader_label'] = df['vader_compound'].apply(vader_label)

# ── 4. STATISTICS ──────────────────────────────────────────
print("=== VADER Label Distribution ===")
print(df['vader_label'].value_counts())

r, p = stats.pearsonr(df['score'], df['vader_compound'])
print(f"\nPearson r (score vs sentiment): {r:.4f}, p={p:.4e}")

groups = [g['vader_compound'].values for _, g in df.groupby('source')]
f_stat, p_anova = stats.f_oneway(*groups)
print(f"ANOVA across sources: F={f_stat:.4f}, p={p_anova:.4e}")

r2, p2 = stats.pearsonr(df['vader_compound'], df['tb_polarity'])
print(f"VADER vs TextBlob correlation: r={r2:.4f}, p={p2:.4e}")

# ── 5. VISUALIZATIONS ──────────────────────────────────────
# (All 6 figures — see full script for details)
# Figure 1: Histogram of VADER compound scores
# Figure 2: Weekly rolling sentiment by platform
# Figure 3: Bar chart by community
# Figure 4: Scatter — engagement vs sentiment
# Figure 5: Heatmap day-of-week vs hour
# Figure 6: VADER vs TextBlob agreement

# ── 6. TF-IDF KEYWORDS ─────────────────────────────────────
print("\n=== Top TF-IDF Terms by Sentiment Class ===")
for label in ['Positive', 'Neutral', 'Negative']:
    corpus = df[df['vader_label'] == label]['clean_text'].tolist()
    tfidf = TfidfVectorizer(max_features=10, stop_words='english')
    tfidf.fit(corpus)
    print(f"{label}: {list(tfidf.get_feature_names_out())}")
