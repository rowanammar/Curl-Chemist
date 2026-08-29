import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from firestore_helpers import get_all_products, get_active_conflicts

products = get_all_products()
conflicts = get_active_conflicts()

print("=== PRODUCTS ON SHELF ===")
for p in products:
    print(f"- Keys: {list(p.keys())}")
    print(f"  Brand: {p.get('brand')} | Name field?: {p.get('product_name') or p.get('name_en') or p.get('productName')} (ID: {p.get('id')})")


print("\n=== ACTIVE CONFLICTS ===")
for c in conflicts:
    print(f"- Keys: {list(c.keys())}")
    print(c)
