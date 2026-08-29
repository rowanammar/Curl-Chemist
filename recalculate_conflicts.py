import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from firestore_helpers import get_all_products, clear_all_conflicts, save_conflict
from agents.chemist_agent import check_product_conflicts

async def main():
    products = get_all_products()
    print(f"Loaded {len(products)} products.")
    print("Clearing old conflicts...")
    clear_all_conflicts()
    
    print("Running new conflict detection...")
    conflicts = await check_product_conflicts(products)
    
    print(f"Found {len(conflicts)} conflicts.")
    for c in conflicts:
        save_conflict(c)
        print(f"- Saved conflict: {c.get('severity')} | {c.get('product_a_name')} and {c.get('product_b_name')}")

if __name__ == "__main__":
    asyncio.run(main())
