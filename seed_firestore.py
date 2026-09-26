import datetime
import google.auth
from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-02-610e200fc759"
COLLECTION_NAME = "financial_metrics"

SEED_DATA = [
    {
        "ticker": "JPMC",
        "name": "JPMorgan Chase & Co.",
        "accounting_standard": "US GAAP",
        "currency": "USD",
        "fiscal_year": "FY2025",
        "revenue_billions": 158.10,
        "net_income_billions": 49.60,
        "net_margin_percent": 31.37,
        "roe_percent": 16.80,
    },
    {
        "ticker": "GS",
        "name": "Goldman Sachs Group Inc.",
        "accounting_standard": "US GAAP",
        "currency": "USD",
        "fiscal_year": "FY2025",
        "revenue_billions": 46.25,
        "net_income_billions": 8.52,
        "net_margin_percent": 18.42,
        "roe_percent": 11.20,
    },
    {
        "ticker": "ACN",
        "name": "Accenture plc",
        "accounting_standard": "US GAAP",
        "currency": "USD",
        "fiscal_year": "FY2025",
        "revenue_billions": 64.90,
        "net_income_billions": 7.35,
        "net_margin_percent": 11.33,
        "roe_percent": 27.50,
    },
    {
        "ticker": "TCS",
        "name": "Tata Consultancy Services",
        "accounting_standard": "IndAS",
        "currency": "INR",
        "fiscal_year": "FY2025",
        "revenue_billions": 2408.93,
        "net_income_billions": 465.80,
        "net_margin_percent": 19.34,
        "roe_percent": 48.20,
    },
    {
        "ticker": "INFY",
        "name": "Infosys Limited",
        "accounting_standard": "IFRS",
        "currency": "INR",
        "fiscal_year": "FY2025",
        "revenue_billions": 1536.70,
        "net_income_billions": 262.48,
        "net_margin_percent": 17.08,
        "roe_percent": 31.40,
    },
]

def seed_firestore():
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/datastore", "https://www.googleapis.com/auth/cloud-platform"])
    db = firestore.Client(project=PROJECT_ID, credentials=credentials)
    collection_ref = db.collection(COLLECTION_NAME)
    print(f"Seeding Firestore collection '{COLLECTION_NAME}' for project '{PROJECT_ID}'...")

    for item in SEED_DATA:
        item["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        doc_ref = collection_ref.document(item["ticker"])
        doc_ref.set(item)
        print(f"  ✓ Seeded {item['ticker']} ({item['name']})")

    print("Seeding complete!")

if __name__ == "__main__":
    seed_firestore()
