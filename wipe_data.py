from google.cloud import firestore
from config import DEMO_USER_ID

db = firestore.Client()
user_ref = db.collection("users").document(DEMO_USER_ID)

collections_to_wipe = [
    "products", 
    "conflicts", 
    "routines", 
    "wash_history", 
    "reports", 
    "pipeline_logs", 
    "profile"
]

print(f"Wiping all data for user {DEMO_USER_ID}...")

for coll_name in collections_to_wipe:
    docs = user_ref.collection(coll_name).stream()
    count = 0
    for doc in docs:
        doc.reference.delete()
        count += 1
    print(f"Deleted {count} documents from '{coll_name}'.")

print("All saved data wiped successfully. The database is clean!")
