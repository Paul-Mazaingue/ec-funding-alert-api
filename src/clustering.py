'''
Le but ici est de faire du clustering sur les données des dernières alertes

Pour ceci, nous allons utiliser ces données :

summary

Metadata :

keywords
destination -> facet
title
focusArea -> facet
destinationDetails
destinationGroup -> facet
callTitle
frameworkProgramme -> facet
descriptionByte
programmeDivision -> facet
crossCuttingPriorities
typesOfAction
tags

'''

import pandas as pd, json, html, re, umap
from sentence_transformers import SentenceTransformer
import hdbscan, keybert
from sklearn.feature_extraction.text import TfidfVectorizer
import os
import numpy as np

# --- Load & flatten -----------------
data = json.load(open('../config/alerts.json', 'r', encoding='utf-8'))
records = []
for alert in data:
    for ao in alert['lastDetails']:
        records.append(ao)
df = pd.json_normalize(records)

# --- Clean --------------------------
def strip_html(x):
    return re.sub('<[^<]+?>', ' ', html.unescape(x or ''))

def build_text(row):
    parts = []
    
    # Handle title - ensure it's a list
    title = row.get('title', [])
    if isinstance(title, list):
        parts.append(" ".join(title))
    else:
        parts.append(str(title))
    
    # Add summary if exists
    parts.append(row.get('summary', ''))
    
    # Handle keywords - ensure it's a list
    keywords = row.get('keywords', [])
    if isinstance(keywords, list):
        parts.append(" ".join(keywords))
    else:
        parts.append(str(keywords))
    
    # Handle tags - ensure it's a list
    tags = row.get('tags', [])
    if isinstance(tags, list):
        parts.append(" ".join(tags))
    else:
        parts.append(str(tags))
    
    # Add destination
    parts.append(str(row.get('destination', '')))
    
    # Handle callTitle - ensure it's a list
    call_title = row.get('callTitle', [''])
    if isinstance(call_title, list) and len(call_title) > 0:
        parts.append(call_title[0])
    else:
        parts.append(str(call_title))
    
    return strip_html(" ".join(parts))

df['clean_text'] = df.apply(build_text, axis=1)

# --- Embeddings ---------------------
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
emb = model.encode(df['clean_text'].tolist(), normalize_embeddings=True)

# --- Clustering ---------------------
# Lowering min_cluster_size and min_samples to be more lenient
# Square root of total records was likely too large
clusterer = hdbscan.HDBSCAN(min_cluster_size=5,  # Lower min_cluster_size 
                            min_samples=2,       # Lower min_samples
                            metric='euclidean',
                            cluster_selection_epsilon=0.3)  # More lenient cluster boundary
labels = clusterer.fit_predict(emb)
df['cluster'] = labels

# --- Keywords per cluster -----------
tfidf = TfidfVectorizer(max_features=5000, ngram_range=(1,3))
tfidf_matrix = tfidf.fit_transform(df['clean_text'])
terms = tfidf.get_feature_names_out()

def top_terms(c):
    # Convert pandas Series to boolean numpy array
    idx = (df['cluster'] == c).values
    if idx.sum() == 0:
        return "No terms found"
    sub = tfidf_matrix[idx].mean(axis=0).A1
    top = sub.argsort()[-3:][::-1]
    return ", ".join(terms[t] for t in top)

titles = {c: top_terms(c) for c in set(labels) if c != -1}

# --- Save detailed results -----------
# Save the full dataframe with cluster assignments
df_output = df.copy()
df_output['cluster'] = df_output['cluster'].apply(lambda x: f"Cluster {x}" if x != -1 else "Noise")
df_output.to_csv('../cluster_assignments.csv', index=False)

# Save cluster details separately
cluster_details = []
for c in sorted(set(labels)):
    if c != -1:
        cluster_data = df[df['cluster'] == c]
        # Get top terms
        cluster_terms = top_terms(c)
        # Get example titles for this cluster (up to 3)
        example_titles = []
        for _, row in cluster_data.head(3).iterrows():
            if isinstance(row.get('title', []), list):
                title = " ".join(row['title'])
            else:
                title = str(row.get('title', 'No title'))
            example_titles.append(title)
        
        cluster_details.append({
            'cluster_id': int(c),  # Convert numpy int64 to Python int
            'size': int(len(cluster_data)),  # Convert numpy int64 to Python int
            'top_terms': cluster_terms,
            'example_titles': example_titles
        })

# Custom JSON encoder to handle numpy types
class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return json.JSONEncoder.default(self, obj)

# Save cluster details to a JSON file
with open('../cluster_details.json', 'w', encoding='utf-8') as f:
    json.dump(cluster_details, f, indent=2, ensure_ascii=False, cls=NumpyEncoder)

print(f"\nCluster details saved to '../cluster_details.json'")
print(f"Full data with cluster assignments saved to '../cluster_assignments.csv'")

# Create statistics summary
with open('../cluster_summary.txt', 'w', encoding='utf-8') as f:
    f.write("# Clustering Results Summary\n\n")
    f.write(f"Total records: {len(df)}\n")
    f.write(f"Records in clusters: {sum(labels != -1)}\n")
    f.write(f"Percentage clustered: {sum(labels != -1)/len(df)*100:.1f}%\n")
    f.write(f"Number of clusters: {len(set(labels) - {-1})}\n\n")
    
    f.write("## Top terms per cluster:\n\n")
    for c, t in sorted(titles.items()):
        count = sum(labels == c)
        f.write(f"Cluster {c} ({count} records): {t}\n")
    
    f.write(f"\nNoise points: {sum(labels == -1)} records\n")

print("Summary statistics saved to '../cluster_summary.txt'")
print(f"\nTotal records: {len(df)}")
print(f"Records in clusters: {sum(labels != -1)}")
print(f"Percentage clustered: {sum(labels != -1)/len(df)*100:.1f}%")
print(f"Number of clusters: {len(set(labels) - {-1})}")