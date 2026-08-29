import json

RULES_PATH = r"d:\Curl-Chemist\data\conflict_rules.json"

with open(RULES_PATH, "r") as f:
    rules = json.load(f)

# 1. Remove missing_cleanser
rules = [r for r in rules if r.get("id") != "missing_cleanser"]

# 2. Update silicone, mineral oil, and wax rules
for r in rules:
    if r.get("id") == "silicone_sulfate_free":
        r["id"] = "silicone_buildup"
        if "trigger_b" in r:
            del r["trigger_b"]
        r["condition"] = "no_sulfate_cleanser_in_shelf"
        r["explanation"] = "You are using non-water-soluble silicones like {a}, but you don't have a sulfate-based clarifying shampoo on your shelf to wash them out. This causes progressive buildup, making hair limp, greasy, and unable to absorb moisture."
    elif r.get("id") == "mineral_oil_buildup":
        if "trigger_b" in r:
            del r["trigger_b"]
        r["condition"] = "no_sulfate_cleanser_in_shelf"
        r["explanation"] = "Mineral oil ({a}) creates a heavy coating. Since you don't have a sulfate-based cleanser on your shelf to effectively wash it out, it will lead to severe buildup."
    elif r.get("id") == "wax_buildup":
        if "trigger_b" in r:
            del r["trigger_b"]
        r["condition"] = "no_sulfate_cleanser_in_shelf"
        r["explanation"] = "Waxes like {a} are extremely difficult to remove without sulfate-based cleansers. Without one on your shelf, wax residue will build up, causing progressive weight and dullness."

with open(RULES_PATH, "w") as f:
    json.dump(rules, f, indent=2)

print("Rules updated successfully.")
