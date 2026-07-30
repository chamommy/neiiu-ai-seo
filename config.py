from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

KNOWLEDGE_FILE = (
    BASE_DIR
    / "knowledge"
    / "seo_knowledge.json"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/120 Safari/537.36"
)

REQUEST_TIMEOUT = 20

RULES_FILE = BASE_DIR / "knowledge" / "seo_rules.json"
REPORTS_DIR = BASE_DIR / "database" / "reports"
CACHE_DIR = BASE_DIR / "database" / "cache"
ENTITY_FILE = BASE_DIR / "knowledge" / "seo_entities.json"
