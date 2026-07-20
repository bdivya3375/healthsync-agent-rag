import sys
sys.path.insert(0, '.')
from services.rag_knowledge import seed_knowledge_base, query_knowledge_base

# Seed the knowledge base
count = seed_knowledge_base(force=True)
print("Seeded {} documents".format(count))

# Test query 1: Drug interaction
print("\n--- Query: Metformin + Ibuprofen ---")
results = query_knowledge_base("patient is on Metformin and Ibuprofen")
for r in results:
    print("  [{}] (dist={:.3f}) {}...".format(r["category"], r["distance"], r["text"][:100]))

# Test query 2: Blood group conflict
print("\n--- Query: Blood group mismatch ---")
results = query_knowledge_base("blood group is different across hospitals")
for r in results:
    print("  [{}] (dist={:.3f}) {}...".format(r["category"], r["distance"], r["text"][:100]))

# Test query 3: Aspirin allergy
print("\n--- Query: Aspirin allergy with Ibuprofen ---")
results = query_knowledge_base("patient has aspirin allergy and is on ibuprofen")
for r in results:
    print("  [{}] (dist={:.3f}) {}...".format(r["category"], r["distance"], r["text"][:100]))

print("\nRAG is working!")
