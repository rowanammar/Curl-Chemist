import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from firestore_helpers import get_all_products, get_active_conflicts

products = get_all_products()
conflicts = get_active_conflicts()

print("=== PRODUCTS ON SHELF ===")
for p in products:
    print(f"- {p.get('brand')} {p.get('name')} (ID: {p.get('id')})")
    print(f"  Ingredients: {', '.join(p.get('ingredients', []))}")

print("\n=== ACTIVE CONFLICTS ===")
for c in conflicts:
    print(f"- Type: {c.get('conflict_type')} | Severity: {c.get('severity')}")
    print(f"  Description: {c.get('description')}")
    if c.get('product_a_id') and c.get('product_b_id'):
        print(f"  Involves: {c.get('product_a_id')} and {c.get('product_b_id')}")
    elif c.get('product_id'):
        print(f"  Involves: {c.get('product_id')}")
