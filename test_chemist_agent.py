
import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.chemist_agent import check_product_conflicts

# Mock products
COWASH = {
    "id": "cowash1",
    "product_name": "Coconut CoWash",
    "ingredients": [{"name": "cocamidopropyl betaine"}, {"name": "cetearyl alcohol"}]
}

HEAVY_SILICONE = {
    "id": "silicone1",
    "product_name": "Heavy Silicone Conditioner",
    "ingredients": [{"name": "amodimethicone"}, {"name": "dimethicone"}]
}

CLARIFYING_SHAMPOO = {
    "id": "clarifier1",
    "product_name": "Purifying Shampoo",
    "ingredients": [{"name": "sodium laureth sulfate"}, {"name": "citric acid"}]
}

DEEP_CONDITIONER = {
    "id": "dc1",
    "product_name": "Moisture Deep Conditioner",
    "ingredients": [{"name": "shea butter"}, {"name": "water"}]
}

LEAVE_IN = {
    "id": "leavein1",
    "product_name": "Light Leave-In",
    "ingredients": [{"name": "water"}, {"name": "glycerin"}]
}

async def test_cowash_silicone_conflict():
    print("Testing CoWash + Silicone without clarifier...")
    conflicts = await check_product_conflicts([COWASH, HEAVY_SILICONE])
    assert len(conflicts) > 0, "Expected a conflict to be flagged"
    assert any(c["product_a_id"] in ["cowash1", "silicone1"] for c in conflicts)

async def test_cowash_silicone_mitigated_by_clarifier():
    print("Testing CoWash + Silicone WITH clarifier...")
    conflicts = await check_product_conflicts([COWASH, HEAVY_SILICONE, CLARIFYING_SHAMPOO])
    silicone_conflict = [c for c in conflicts if c.get("severity") == "critical" and "silicone" in c.get("explanation", "").lower()]
    assert len(silicone_conflict) == 0, "Mitigated conflict was incorrectly flagged"

async def test_clarifying_without_deep_conditioner():
    print("Testing Clarifying Shampoo without Deep Conditioner...")
    # Need at least 2 products to bypass the early return
    conflicts = await check_product_conflicts([CLARIFYING_SHAMPOO, LEAVE_IN])
    dc_conflict = [c for c in conflicts if "deep condition" in c.get("explanation", "").lower()]
    assert len(dc_conflict) > 0, "Expected 'missing deep conditioner' conflict"

async def test_clarifying_with_deep_conditioner():
    print("Testing Clarifying Shampoo WITH Deep Conditioner...")
    conflicts = await check_product_conflicts([CLARIFYING_SHAMPOO, DEEP_CONDITIONER])
    dc_conflict = [c for c in conflicts if "deep condition" in c.get("explanation", "").lower()]
    assert len(dc_conflict) == 0, "Missing deep conditioner conflict was incorrectly flagged"


if __name__ == "__main__":
    asyncio.run(test_cowash_silicone_conflict())
    asyncio.run(test_cowash_silicone_mitigated_by_clarifier())
    asyncio.run(test_clarifying_without_deep_conditioner())
    asyncio.run(test_clarifying_with_deep_conditioner())
    print("All tests passed!")
