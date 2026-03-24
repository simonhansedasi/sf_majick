import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    confusion_matrix, classification_report,
)

# ── Load data ─────────────────────────────────────────────────────────────────

df = pd.read_pickle('../sim/data/df.pkl')

# ── Collapse closed stages ────────────────────────────────────────────────────

closed_stages = [
    "Closed Won",
    "Closed Lost",
    "Closed Dead",
    "Closed Converted"
]

df["stage_final"] = df["stage_final"].replace(closed_stages, "Closed")

# ── One-hot encode stage_final ────────────────────────────────────────────────

stage_dummies = pd.get_dummies(df['stage_final'], prefix='stage')
df = pd.concat([df, stage_dummies], axis=1)

df.drop(columns=['stage_final'], inplace=True)

# ── One-hot encode rep_id ─────────────────────────────────────────────────────

stage_dummies = pd.get_dummies(df['rep_id'], prefix='rep')
df = pd.concat([df, stage_dummies], axis=1)

df.drop(columns=['rep_id'], inplace=True)

# ── Engineer engagement consistency ──────────────────────────────────────────

min_activity = 3
df['engagement_consistency'] = np.where(
    df['activity_count'] >= min_activity,
    1 - np.abs(df['early_activity'] - df['late_activity']) / df['activity_count'],
    0
)

# ── Drop non-feature columns ──────────────────────────────────────────────────

df = df.drop(columns=['run_id', 'entity', 'sentiment_median', 'sentiment_std',
                       'n_stages', 'pipeline_depth', 'is_lead'])

# ── Fill missing values ───────────────────────────────────────────────────────

df['commission'] = df['commission'].fillna(0)
df['momentum_slope'] = df['momentum_slope'].fillna(0)

# ── Prepare features and target ───────────────────────────────────────────────

X = df.drop(columns=['won'])
y = df['won']

# ── Train-test split ──────────────────────────────────────────────────────────

X_train, X_test, y_train, y_test = train_test_split(
    X, y,
    test_size=0.25,
    stratify=y,
    random_state=42
)

# ── Train Random Forest ───────────────────────────────────────────────────────

rf = RandomForestClassifier(
    n_estimators=200,
    random_state=8493,
    max_depth=7,
    min_samples_split=15,
    min_samples_leaf=7,
    max_features='sqrt',
    class_weight='balanced',
    n_jobs=-1
)

rf.fit(X_train, y_train)
y_pred = rf.predict(X_test)

# ── Metrics ───────────────────────────────────────────────────────────────────

print("Accuracy:", accuracy_score(y_test, y_pred))
print("Precision:", precision_score(y_test, y_pred))
print("Recall:", recall_score(y_test, y_pred))
print("F1 Score:", f1_score(y_test, y_pred))
print("\nConfusion Matrix:\n", confusion_matrix(y_test, y_pred))
print("\nClassification Report:\n", classification_report(y_test, y_pred))

# ── Feature importance plot ───────────────────────────────────────────────────

importances = rf.feature_importances_
features = X.columns

idx = np.argsort(importances)[::-1][:15]

plt.figure(figsize=(10, 6))
plt.bar(range(len(idx)), importances[idx])
plt.xticks(range(len(idx)), features[idx], rotation=75)
plt.title("Top Drivers of Winning Deals")
plt.show()

for feat, imp in zip(features, importances):
    print(feat, imp)

# ── Win rate analysis + sale potential ───────────────────────────────────────

# --- Step 1: Clip outliers ---
def clip_outliers(series, lower=0.01, upper=0.99):
    low_val = series.quantile(lower)
    high_val = series.quantile(upper)
    return series.clip(lower=low_val, upper=high_val)

df['stage_clipped'] = clip_outliers(df['stage_velocity'], lower=0.00, upper=0.99)
df['activity_clipped'] = clip_outliers(df['activity_velocity'], lower=0.00, upper=0.99)
df['consistency_clipped'] = clip_outliers(df['engagement_consistency'], lower=0.00, upper=0.99)

# --- Step 2: Normalize 0-1 ---
df['stage_velocity_norm'] = (df['stage_clipped'] - df['stage_clipped'].min()) / (df['stage_clipped'].max() - df['stage_clipped'].min())
df['activity_velocity_norm'] = (df['activity_clipped'] - df['activity_clipped'].min()) / (df['activity_clipped'].max() - df['activity_clipped'].min())
df['engagement_consistency_norm'] = (df['consistency_clipped'] - df['consistency_clipped'].min()) / (df['consistency_clipped'].max() - df['consistency_clipped'].min())

# --- Step 3: Per-bin win rates ---
n_bins = 20
def per_bin_win_rate(series, won, bins):
    bin_idx = np.digitize(series, bins) - 1
    bin_idx = np.clip(bin_idx, 0, len(bins)-2)
    df_tmp = won.groupby(bin_idx).mean()
    df_tmp = df_tmp.reindex(np.arange(len(bins)-1), fill_value=np.nan)
    return df_tmp.interpolate()

stage_bins = np.linspace(df["stage_velocity_norm"].min(), df["stage_velocity_norm"].max(), n_bins+1)
activity_bins = np.linspace(df["activity_velocity_norm"].min(), df["activity_velocity_norm"].max(), n_bins+1)
consistency_bins = np.linspace(df["engagement_consistency_norm"].min(), df["engagement_consistency_norm"].max(), n_bins+1)

stage_win = per_bin_win_rate(df["stage_velocity_norm"], df["won"], stage_bins)
activity_win = per_bin_win_rate(df["activity_velocity_norm"], df["won"], activity_bins)
consistency_win = per_bin_win_rate(df["engagement_consistency_norm"], df["won"], consistency_bins)

# --- Step 4: Compute Sale Potential and Confidence Interval ---
metric_matrix = np.vstack([stage_win, activity_win, consistency_win])  # shape: (3, n_bins)
weights = np.array([0.4, 0.4, 0.2])

sale_potential = (weights @ metric_matrix)  # weighted sum per bin
# Compute standard deviation across metrics for each bin
potential_std = np.sqrt(np.sum((weights[:, None]**2) * (metric_matrix - metric_matrix.mean(axis=0))**2, axis=0))

# 95% CI (approx) using ±1.96*std
ci_upper = sale_potential + 1.96*potential_std
ci_lower = sale_potential - 1.96*potential_std

# --- Step 5: Plot ---
x_common = np.linspace(0, 1, n_bins)
mean_win = df['won'].mean()

plt.figure(figsize=(12, 6))
plt.plot(x_common, stage_win, marker='o', label="Stage Velocity", color='tab:blue', alpha=0.5)
plt.plot(x_common, activity_win, marker='o', label="Activity Velocity", color='tab:orange', alpha=0.5)
plt.plot(x_common, consistency_win, marker='o', label="Engagement Consistency", color='tab:green', alpha=0.5)
plt.plot(x_common, sale_potential, marker='o', label="Sale Potential", color='black', linewidth=2)
plt.fill_between(x_common, ci_lower, ci_upper, color='black', alpha=0.15, label='Potential 95% CI')
plt.axhline(mean_win, color='gray', linestyle='--', linewidth=1.5, label='Overall Mean Win Rate')

plt.xlabel("Normalized Value", fontsize=15)
plt.ylabel("Win Rate", fontsize=15)
plt.title("Sales Pipeline Metrics\n& Derived Sale Potential", fontsize=20)
plt.xticks(fontsize=12)
plt.yticks(fontsize=12)
plt.legend(fontsize=12)
plt.grid(alpha=0.3)
plt.savefig('win_rate_metrix.png')
plt.show()
