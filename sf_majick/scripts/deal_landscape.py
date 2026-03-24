import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from collections import defaultdict
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans, DBSCAN
from sklearn.manifold import TSNE
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    confusion_matrix, classification_report,
)
from tqdm import tqdm

# ── Load data ─────────────────────────────────────────────────────────────────

df = pd.read_pickle('../sim/data/df.pkl')

# ── Extract feature columns (everything from col index 6 onward) ──────────────

col_list = df.columns.to_list()
features = col_list[6:]

# ── Scale + elbow method for K-Means ─────────────────────────────────────────

features_for_clustering = features
X = df[features_for_clustering].fillna(0)

scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

inertia = []
K_range = range(1, 10)
for k in K_range:
    km = KMeans(n_clusters=k, random_state=24543)
    km.fit(X_scaled)
    inertia.append(km.inertia_)

plt.figure(figsize=(8, 5))
plt.plot(K_range, inertia, marker='o')
plt.xlabel("Number of clusters")
plt.ylabel("Inertia (sum of squared distances)")
plt.title("Elbow Method to choose number of clusters")
plt.show()

# ── Train Random Forest classifier ───────────────────────────────────────────

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

X_train, X_test, y_train, y_test = train_test_split(
    X_scaled, df['won'], test_size=0.3, random_state=8493, stratify=df['won']
)

rf.fit(X_train, y_train)
y_pred = rf.predict(X_test)

print("Accuracy:", accuracy_score(y_test, y_pred))
print("Precision:", precision_score(y_test, y_pred))
print("Recall:", recall_score(y_test, y_pred))
print("F1 Score:", f1_score(y_test, y_pred))
print("\nConfusion Matrix:\n", confusion_matrix(y_test, y_pred))
print("\nClassification Report:\n", classification_report(y_test, y_pred))

# ── Behavioral PCA (canonical path) ──────────────────────────────────────────

# ---- Step 1: Scale behavioral features (exclude win_prob) ----
behavior_features = features.copy()  # your activity/stage metrics
X_behavior = df[behavior_features].values

# scaler = StandardScaler()
scaler = MinMaxScaler(feature_range=(-1, 1))

X_scaled = scaler.fit_transform(X_behavior)  # mean=0, std=1

# ---- Step 2: PCA on behavioral features only ----
pca = PCA(n_components=9)
X_pca = pca.fit_transform(X_scaled)

df['PC1'] = X_pca[:,0]
df['PC2'] = X_pca[:,1]

# ---- Step 3: Cluster on PCs (optional) ----
k = 3  # or elbow method
kmeans = KMeans(n_clusters=k, random_state=42)
df['cluster'] = kmeans.fit_predict(X_pca)

# ---- Step 4: Overlay win probability ----
# Already computed from your RF
# df['win_prob_rf'] = rf.predict_proba(X_behavior)[:,1]

# ── Compute win probability ───────────────────────────────────────────────────

df['win_prob_rf'] = rf.predict_proba(X_scaled)[:,1]

# ── Supervised PCA scatter (win_prob overlay) ─────────────────────────────────

plt.figure(figsize=(10, 8))
scatter = plt.scatter(
    df['PC1'], df['PC2'],
    c=df['win_prob_rf'],
    cmap='viridis',
    alpha=1,
    s=50
)
plt.colorbar(scatter, label="Win Probability")
plt.xlabel("PC1")
plt.ylabel("PC2")
plt.title("Deals in Behavioral PCA Space (Win Probability Overlay)")
plt.show()

# ── Commission vs win probability ─────────────────────────────────────────────

plt.scatter(df['commission'], df['win_prob_rf'], c=df['cluster'], alpha=0.1)
plt.show()

# ── PCA loadings ──────────────────────────────────────────────────────────────

loadings = pd.DataFrame(
    pca.components_.T,
    index=features,
    columns=[f"PC{i+1}" for i in range(pca.n_components_)]
)

# ── t-SNE on PCA output ───────────────────────────────────────────────────────

tsne = TSNE(
    n_components=2,
    perplexity=30,
    learning_rate=200,
    n_iter=1000,
    random_state=874242
)
X_tsne = tsne.fit_transform(X_pca)

df['TSNE1'] = X_tsne[:,0]
df['TSNE2'] = X_tsne[:,1]

# ── t-SNE: win probability overlay ───────────────────────────────────────────

plt.figure(figsize=(10, 8))
scatter = plt.scatter(
    df['TSNE1'], df['TSNE2'],
    c=df['win_prob_rf'],
    cmap='coolwarm',
    alpha=0.37,
    s=50
)
plt.colorbar(scatter, label="Win Probability")
plt.xlabel("t-SNE1")
plt.ylabel("t-SNE2")
plt.title("Deals in Organic Behavioral Space (t-SNE)")
plt.savefig('tsne.png')
plt.show()

# ── t-SNE: avg days in stage ──────────────────────────────────────────────────

plt.figure(figsize=(10, 8))
plt.scatter(df.TSNE1, df.TSNE2,
            c=df.avg_days_in_stage,
            cmap='coolwarm', alpha=0.37)
plt.colorbar(label="Avg Days in Stage")
plt.show()

# ── t-SNE: stage velocity ─────────────────────────────────────────────────────

plt.figure(figsize=(10, 8))
plt.scatter(df.TSNE1, df.TSNE2,
            c=df.stage_velocity,
            cmap="coolwarm")
plt.colorbar(label="Stage Velocity")
plt.show()

# ── t-SNE: colored by rep, sized by win probability ──────────────────────────

color_map = {
    '005ak00000TI3rZAAT': '#e41a1c',
    '005ak00000TI0yYAAT': '#377eb8',
    '005ak00000TI49JAAT': '#4daf4a',
    '005ak00000TI4KbAAL': '#984ea3'
}

plt.figure(figsize=(10, 8))
colors = df['rep_id'].map(color_map).fillna('#cccccc')
sc = plt.scatter(df.TSNE1, df.TSNE2,
                 c=colors,
                 cmap="coolwarm",
                 alpha=0.7,
                 s=(df['win_prob_rf'] + 1e-3) * 250)

plt.xticks([])
plt.yticks([])
cbar = plt.colorbar(sc)
cbar.set_label('Normalized Value', fontsize=16)
cbar.ax.tick_params(labelsize=12)
plt.title(f"Deal Behavior Landscape:", fontsize=18)
plt.tight_layout()
plt.show()

# ── Win probability histogram ─────────────────────────────────────────────────

plt.hist(df['win_prob_rf'])
plt.show()

# ── Per-feature t-SNE scatter plots ──────────────────────────────────────────

for feat in features:
    plt.figure(figsize=(10, 8))
    df = df.sort_values(feat, ascending=True)

    low, high = df[feat].quantile([0.01, 0.99])
    feat_clip = df[feat].clip(low, high)

    feat_norm = (feat_clip - feat_clip.min()) / (feat_clip.max() - feat_clip.min())
    sc = plt.scatter(df.TSNE1, df.TSNE2,
                     c=feat_norm,
                     cmap="coolwarm",
                     alpha=0.7,
                     s=(df['win_prob_rf'] + 1e-3) * 75)

    cbar = plt.colorbar(sc)
    cbar.set_label('Normalized Value', fontsize=16)
    cbar.ax.tick_params(labelsize=12)
    plt.title(f"Deal Behavior Landscape: {feat}", fontsize=18)
    plt.tight_layout()
    plt.show()

# ── K-Means on t-SNE space (trajectory clustering) ───────────────────────────

N_CLUSTERS = 15
RANDOM_STATE = 42

X = df[['TSNE1', 'TSNE2']].values

kmeans = KMeans(n_clusters=N_CLUSTERS, random_state=RANDOM_STATE)
df['cluster'] = kmeans.fit_predict(X)

centroids = kmeans.cluster_centers_

# ── Build trajectories ────────────────────────────────────────────────────────

df = df.sort_values('entity')

# Build sequences
trajectories = (
    df.groupby('entity')['cluster']
    .apply(list)
    .to_dict()
)

# ── Collapse sequences ────────────────────────────────────────────────────────

def collapse_sequence(seq):
    collapsed = [seq[0]]
    for s in seq[1:]:
        if s != collapsed[-1]:
            collapsed.append(s)
    return collapsed

collapsed_trajectories = {
    k: collapse_sequence(v)
    for k, v in trajectories.items()
}

# ── Count transitions ─────────────────────────────────────────────────────────

transition_counts = defaultdict(int)

for seq in collapsed_trajectories.values():
    for i in range(len(seq) - 1):
        a, b = seq[i], seq[i+1]
        transition_counts[(a, b)] += 1

trans_df = pd.DataFrame([
    {'from': k[0], 'to': k[1], 'count': v}
    for k, v in transition_counts.items()
])

# ── Attach outcomes to trajectories ──────────────────────────────────────────

def get_outcome(deal_df):
    if (deal_df['won'] == True).any():
        return 'won'
    elif (deal_df['won'] == False).any():
        return 'lost'
    else:
        return 'open'

outcomes = df.groupby('entity').apply(get_outcome)

traj_df = pd.DataFrame({
    'deal_id': list(collapsed_trajectories.keys()),
    'trajectory': list(collapsed_trajectories.values())
})

traj_df['outcome'] = traj_df['deal_id'].map(outcomes)

# ── Sample trajectories ───────────────────────────────────────────────────────

SAMPLE_SIZE = 50

sampled = (
    traj_df.groupby('outcome', group_keys=False)
    .apply(lambda x: x.sample(min(len(x), SAMPLE_SIZE), random_state=42))
)

# ── Plot sampled trajectories ─────────────────────────────────────────────────

plt.figure(figsize=(10, 10))

plt.scatter(df['TSNE1'], df['TSNE2'], alpha=0.05, s=5)

for _, row in sampled.iterrows():
    seq = row['trajectory']
    coords = np.array([centroids[s] for s in seq])

    if row['outcome'] == 'won':
        color = 'green'
    elif row['outcome'] == 'lost':
        color = 'red'
    else:
        color = 'gray'

    plt.plot(coords[:, 0], coords[:, 1], color=color, alpha=0.6)

plt.scatter(centroids[:, 0], centroids[:, 1], c='black', s=50)

plt.title("Sampled Deal Trajectories (Cluster Space)")
plt.show()

# ── DBSCAN regional analysis ──────────────────────────────────────────────────

dfy = df.copy()

X = StandardScaler().fit_transform(dfy[['TSNE1', 'TSNE2']])

db = DBSCAN(eps=0.12, min_samples=2).fit(X)
dfy['region'] = db.labels_

for i in range(len(dfy['region'].unique())):
    dft = dfy[dfy['region'] == i].copy()
    plt.scatter(dft['TSNE1'], dft['TSNE2'], s=(dft['win_prob_rf'] + 1e-3) * 150)
    plt.title(f'region {i}')
    plt.xlim([df['TSNE1'].min()-10, df['TSNE1'].max()+10])
    plt.ylim([df['TSNE2'].min()-10, df['TSNE2'].max()+10])
    plt.show()

print(dfy.groupby('region')['win_prob_rf'].mean())

print(dfy[dfy['region'] == 5][[
    'activity_velocity',
    'stage_velocity',
    'avg_days_in_stage',
    'cycle_time'
]].describe())

print(dfy.groupby('rep_id')['region'].value_counts(normalize=True))

print(dfy.groupby('region')['stage_velocity'].mean().sort_values())

# ── RF to predict region from behavioral features ─────────────────────────────

X = dfy[[
    'activity_velocity',
    'stage_velocity',
    'avg_days_in_stage',
    'cycle_time'
]]
y = dfy['region']
model = RandomForestClassifier()
model.fit(X, y)

importances = pd.Series(model.feature_importances_, index=X.columns)
print(importances.sort_values(ascending=False))

# ── DBSCAN organic clustering (eps=0.5) ───────────────────────────────────────

db = DBSCAN(eps=0.5, min_samples=10)
df['organic_cluster'] = db.fit_predict(X_tsne)

# ── t-SNE axis correlation with features ─────────────────────────────────────

corr_tsne1 = df[features].corrwith(df['TSNE1'])
corr_tsne2 = df[features].corrwith(df['TSNE2'])

tsne_contrib = pd.DataFrame({
    'TSNE1_corr': corr_tsne1,
    'TSNE2_corr': corr_tsne2
}).sort_values('TSNE1_corr', ascending=False)

print(tsne_contrib)

# ── RF regressors for t-SNE axis importance ───────────────────────────────────

rf1 = RandomForestRegressor()
rf1.fit(X_scaled, df['TSNE1'])

rf2 = RandomForestRegressor()
rf2.fit(X_scaled, df['TSNE2'])

importances1 = pd.Series(rf1.feature_importances_, index=features)
importances2 = pd.Series(rf2.feature_importances_, index=features)

print('importance for sne1')
print(importances1)
print('\nimportance for ne2')
print(importances2)
