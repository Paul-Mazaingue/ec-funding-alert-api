import pandas as pd, json, html, re
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
import os
import numpy as np
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
from sklearn.cluster import KMeans
import logging
logging.basicConfig(level=logging.INFO)

from .utils import load_json, save_json

DATA_FOLDER = 'data'
CONFIG_FOLDER = 'config'

custom_stopwords = list(ENGLISH_STOP_WORDS) + [
    # Mots vides classiques (non inclus dans ENGLISH_STOP_WORDS)
    "none", "use", "based", "including", "support", "project", "projects", "des",
    
    # Dates fréquentes
    "2025", "2024", "2023", "2022", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12",
    
    # Éléments Horizon Europe / CORDIS génériques
    "horizon", "cl3", "cl4", "cl5", "eu", "european", "commission", "call",
    "programme", "action", "actions", "research", "innovation", "solutions", "policy",
    
    # Mots trop génériques ou redondants
    "approach", "approaches", "challenge", "challenges", "strategies", "measures",
    "development", "results", "knowledge", "data", "new", "future", "current", "existing",
    
    # Formes grammaticales redondantes
    "using", "ensuring", "improving", "increase", "decrease", "enable", "promote",
    "strengthen", "enhance", "ensure", "develop", "improve",

    # mots clés détecté lors de l'annalyse des mot clés dominants
    "area", "work", "open", "topic", "direct", "europe", "forward", "infra", "ir", 
    "ju", "selection", "partners","carry","activities" 
]

async def cluster_alert(alertName: str, n_clusters: int = 10):
    logging.info(f"Clustering alert: {alertName} with {n_clusters} clusters")

    # load and flatten the data
    df = load_details(alertName)

    # Clean the data
    df['clean_text'] = df.apply(build_text, axis=1)

    # Embeddings
    model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    emb = model.encode(df['clean_text'].tolist(), normalize_embeddings=True)

    # Clustering
    kmeans = KMeans(n_clusters=n_clusters, random_state=42)

    labels = kmeans.fit_predict(emb)
    df['cluster'] = labels

    # Keywords per cluster
    tfidf = TfidfVectorizer(max_features=5000, ngram_range=(1,3), stop_words=custom_stopwords)
    tfidf_matrix = tfidf.fit_transform(df['clean_text'])
    terms = tfidf.get_feature_names_out()

    titles = {c: top_terms(c, df, tfidf_matrix, terms) for c in set(labels)}

    # Save detailed results
    save_cluster_details(df, labels, n_clusters, tfidf_matrix, terms, alertName)


def save_cluster_details(df, labels, n_clusters, tfidf_matrix, terms, alertName):
    # Créer le dossier de sortie si besoin
    os.makedirs('testtmp', exist_ok=True)

    # On vérifie si le fichier existe
    if not os.path.exists(DATA_FOLDER + '/clusters.json'):
        # Créer le fichier clusters.json
        with open(DATA_FOLDER + '/clusters.json', 'w', encoding='utf-8') as f:
            json.dump([], f, indent=2, ensure_ascii=False)

    # Charger le contenu du fichier clusters.json
    clusters = load_json(DATA_FOLDER + '/clusters.json')
    
    # Vérifier si le nom de l'alerte existe déjà
    alert_index = -1
    for i, cluster in enumerate(clusters):
        if alertName in cluster:
            # Si le nom de l'alerte existe déjà, on le supprime
            alert_index = i
            break
    
    if alert_index != -1:
        clusters.pop(alert_index)

    # Créer une nouvelle entrée pour l'alerte
    alert_data = {
        'n_clusters': n_clusters,
        'total_records': len(df),
        'clusters': []
    }

    # Ajouter les détails par cluster
    for c in sorted(set(labels)):
        alert_data['clusters'].append({
            'cluster_id': int(c),
            'size': int(len(df[df['cluster'] == c])),
            'top_terms': top_terms(c, df, tfidf_matrix, terms),
            'generated_title': generate_title(top_terms(c, df, tfidf_matrix, terms))
        })
        print(f"Cluster {c}: {alert_data['clusters'][-1]['size']} records, Top terms: {alert_data['clusters'][-1]['top_terms']}")
        print(f"Generated title: {alert_data['clusters'][-1]['generated_title']}")
    
    # Ajouter les données d'alerte au tableau de clusters
    clusters.append({alertName: alert_data})

    # Sauvegarder le fichier clusters.json
    save_json(clusters, DATA_FOLDER + '/clusters.json')

    # load alerts 
    alerts = load_json(CONFIG_FOLDER + '/alerts.json')
    for alert in alerts:
        if alert['name'] == alertName:
            # Ajoute le numéro de cluster à chaque lastDetails
            for detail in alert.get('lastDetails', []):
                # Trouver la référence correspondante dans df
                ref = detail.get('reference')
                if ref is not None and 'reference' in df.columns:
                    cluster_num = df.loc[df['reference'] == ref, 'cluster']
                    if not cluster_num.empty:
                        detail['cluster'] = int(cluster_num.iloc[0])
                else:
                    # Si pas de référence, utiliser l'index
                    idx = alert['lastDetails'].index(detail)
                    if idx < len(df):
                        detail['cluster'] = int(df.iloc[idx]['cluster'])
    
    # sauvegarder les alertes avec le numéro de cluster
    save_json(alerts, CONFIG_FOLDER + '/alerts.json')



def load_details(alertName: str):
    data = load_json(CONFIG_FOLDER + '/alerts.json')
    records = []
    for alert in data:
        if alert['name'] == alertName:
            for ao in alert['lastDetails']:
                records.append(ao)
    df = pd.json_normalize(records)
    return df

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

def top_terms(c, df, tfidf_matrix, terms):
    idx = (df['cluster'] == c).values
    if idx.sum() == 0:
        return "No terms found"
    sub = tfidf_matrix[idx].mean(axis=0).A1
    top = sub.argsort()[-3:][::-1]
    return ", ".join(terms[t] for t in top)


def generate_title(top_terms):
    # Liste des termes à ne jamais filtrer
    important_terms = {"ai", "sns", "sesar", "efsa", "era", "widera", "cl6", "cl4", "cl3", "life", "soil"}

    # Mots ou fragments à ignorer
    stop_phrases = {"none", "and", "the", "des", "area", "work", "topic", "open"}

    # Vérifier si top_terms est None ou vide
    if not top_terms or top_terms == "No terms found" or pd.isna(top_terms):
        return "Unlabeled Cluster"
        
    # Séparer les mots clés
    try:
        terms = [t.strip() for t in str(top_terms).split(',') if t and t.strip()]
    except:
        return "Unlabeled Cluster"

    # Filtrage plus intelligent : on garde le mot si...
    filtered_terms = []
    for t in terms:
        # Gérer explicitement les valeurs None et NaN
        if t is None or pd.isna(t) or not t:
            continue
        
        try:
            t_lower = str(t).lower()
            if t_lower in important_terms:
                filtered_terms.append(t)
            elif all(word not in stop_phrases for word in t_lower.split()) and len(t_lower) > 2:
                filtered_terms.append(t)
        except:
            continue

    if not filtered_terms:
        return "Unlabeled Cluster"

    # Construction du titre à partir des termes filtrés, avec gestion des cas d'erreur
    try:
        if len(filtered_terms) >= 2:
            title = f"{filtered_terms[0].capitalize()} & {filtered_terms[1].capitalize()}"
            if len(filtered_terms) > 2:
                title += f" ({filtered_terms[2].upper()}-related)"
            return title
        else:
            return filtered_terms[0].capitalize()
    except:
        return "Unlabeled Cluster"

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

if __name__ == "__main__":
    # Example usage
    cluster_alert("test", n_clusters=10)
    print("Clustering completed.")
