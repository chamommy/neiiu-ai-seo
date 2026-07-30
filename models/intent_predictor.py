from pathlib import Path

import joblib


BASE_DIR = Path(__file__).resolve().parent
MODEL_FILE = BASE_DIR / "seo_ai.joblib"


def load_intent_model():
    if not MODEL_FILE.exists():
        raise FileNotFoundError(
            f"Model intent tidak ditemukan: {MODEL_FILE}"
        )

    return joblib.load(MODEL_FILE)


def predict_intent(
    keyword: str,
    model,
) -> dict:
    keyword = keyword.strip().lower()

    if not keyword:
        return {
            "intent": "unknown",
            "confidence": 0.0,
        }

    intent = model.predict([keyword])[0]

    probabilities = model.predict_proba([keyword])[0]
    confidence = round(
        max(probabilities) * 100,
        2,
    )

    return {
        "intent": intent,
        "confidence": confidence,
    }