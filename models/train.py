from pathlib import Path

import joblib
import pandas as pd

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline


BASE_DIR = Path(__file__).resolve().parent

DATASET_FILE = BASE_DIR / "dataset.csv"
MODEL_FILE = BASE_DIR / "seo_ai.joblib"


data = pd.read_csv(DATASET_FILE)

model = Pipeline([
    ("tfidf", TfidfVectorizer()),
    ("classifier", LogisticRegression(max_iter=1000)),
])

model.fit(
    data["keyword"],
    data["intent"],
)

joblib.dump(
    model,
    MODEL_FILE,
)

print("AI berhasil dilatih.")
print(f"Model tersimpan di: {MODEL_FILE}")