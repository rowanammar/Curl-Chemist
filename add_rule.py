import json
import os

RULES_PATH = r"d:\Curl-Chemist\data\conflict_rules.json"

with open(RULES_PATH, "r") as f:
    rules = json.load(f)

new_rule = {
    "id": "missing_cleanser",
    "type": "missing_essential",
    "trigger_a": {"category": "any_product"},
    "condition": "no_cleanser_in_shelf",
    "severity": "critical",
    "explanation": "You have hair products on your shelf, but no shampoo or co-wash. Without a cleanser, your hair will accumulate product buildup, leading to dullness and inability to absorb moisture.",
    "fix": "Add a shampoo (sulfate or sulfate-free) or a co-wash to your shelf to ensure you can remove product buildup."
}

# Only append if not already present
if not any(r.get("id") == "missing_cleanser" for r in rules):
    rules.append(new_rule)
    with open(RULES_PATH, "w") as f:
        json.dump(rules, f, indent=2)
    print("Rule added successfully.")
else:
    print("Rule already exists.")
