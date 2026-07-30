from pathlib import Path

import joblib


BASE_DIR = Path(__file__).resolve().parent
MODEL_FILE = BASE_DIR / "seo_ai.joblib"


model = joblib.load(MODEL_FILE)

print("=" * 40)
print("AI SEO Keyword Intent")
print("=" * 40)

while True:
    keyword = input("\nMasukkan keyword: ").strip()

    if keyword.lower() in {"exit", "keluar"}:
        print("Program selesai.")
        break

    if not keyword:
        print("Keyword tidak boleh kosong.")
        continue

    intent = model.predict([keyword])[0]
    confidence = max(
        model.predict_proba([keyword])[0]
    ) * 100

    print(f"Intent     : {intent}")
    print(f"Confidence : {confidence:.2f}%")