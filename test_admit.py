"""Test the full CrewAI audit with a known conflicting patient."""
import requests
import json
import time

# Step 1: Admit until we get a conflict
print("=" * 60)
print("Simulating admissions until we find a conflict...")
print("=" * 60)

admission_id = None
for i in range(10):
    r = requests.post("http://127.0.0.1:8000/api/v1/admit")
    d = r.json()
    aid = d["admission"]["id"]
    name = d["admission"]["name"]
    hosp = d["admission"]["source_hospital"]
    print(f"  Walk-in #{aid}: {name} from {hosp}")

    # Quick check if this one has history
    r2 = requests.get(f"http://127.0.0.1:8000/api/v1/admissions/{aid}/audit")
    audit = r2.json()
    conflicts = audit.get("conflicts", [])
    history = audit.get("history", [])

    if conflicts:
        admission_id = aid
        print(f"\n  CONFLICT FOUND for {name}!")
        print(f"  History records: {len(history)}")
        print(f"  Conflicts: {len(conflicts)}")
        for c in conflicts:
            print(f"\n  Type: {c['conflict_type']}")
            print(f"  Values: {json.dumps(c['values'], indent=4)}")
            print(f"  Department: {c['department']}")
            print(f"  Confidence: {c['confidence_score']}")
            print(f"\n  === CrewAI RECOMMENDATION ===")
            print(f"  {c['recommendation']}")
        break

if not admission_id:
    print("No conflicts found in 10 admissions. Try again!")
