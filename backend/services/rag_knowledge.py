"""
RAG Knowledge Base for Nurse Joy
=================================
Uses ChromaDB as a local vector store to give Nurse Joy access to
medical reference knowledge (drug interactions, clinical guidelines,
standard treatment protocols).

The knowledge base is seeded once at startup with curated medical
reference documents, then queried at chat-time to augment Nurse Joy's
context with evidence-based information.
"""

import os
import json
import logging
import chromadb
from chromadb.utils import embedding_functions
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ChromaDB Persistent Storage
# ---------------------------------------------------------------------------

_CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(__file__), "..", "rag_store")
_COLLECTION_NAME = "medical_knowledge"

# Use ChromaDB's built-in default embedding function (all-MiniLM-L6-v2)
_embedding_fn = embedding_functions.DefaultEmbeddingFunction()


def _get_collection():
    """Get or create the medical knowledge ChromaDB collection."""
    client = chromadb.PersistentClient(path=_CHROMA_PERSIST_DIR)
    collection = client.get_or_create_collection(
        name=_COLLECTION_NAME,
        embedding_function=_embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )
    return collection


# ---------------------------------------------------------------------------
# Curated Medical Knowledge Documents
# ---------------------------------------------------------------------------

MEDICAL_KNOWLEDGE_DOCS = [
    # ── Drug Interactions ──────────────────────────────────────────────
    {
        "id": "drug_interaction_001",
        "category": "drug_interaction",
        "text": (
            "CRITICAL DRUG INTERACTION: Metformin + Ibuprofen. "
            "NSAIDs like Ibuprofen can reduce renal blood flow and impair kidney function. "
            "In patients taking Metformin for Type 2 Diabetes, concurrent NSAID use increases "
            "the risk of lactic acidosis, a rare but potentially fatal complication. "
            "Recommendation: Monitor renal function (eGFR) closely. Consider Acetaminophen "
            "as an alternative analgesic. If eGFR falls below 30 mL/min, discontinue Metformin."
        ),
    },
    {
        "id": "drug_interaction_002",
        "category": "drug_interaction",
        "text": (
            "DRUG INTERACTION: Lisinopril + Potassium-sparing diuretics (Spironolactone). "
            "ACE inhibitors like Lisinopril increase serum potassium. Combining with "
            "potassium-sparing diuretics can cause dangerous hyperkalemia. "
            "Recommendation: Monitor serum potassium levels within 1 week of co-prescribing. "
            "Target potassium: 3.5-5.0 mEq/L. If K+ > 5.5, discontinue one agent."
        ),
    },
    {
        "id": "drug_interaction_003",
        "category": "drug_interaction",
        "text": (
            "DRUG INTERACTION: Aspirin + Ibuprofen. Concurrent use of Aspirin (for "
            "cardioprotection) with Ibuprofen can reduce the antiplatelet effect of Aspirin. "
            "Ibuprofen competitively blocks COX-1, preventing Aspirin from irreversibly "
            "acetylating it. Recommendation: If both are needed, take Aspirin at least "
            "30 minutes before Ibuprofen, or use a non-interfering NSAID like Diclofenac."
        ),
    },
    {
        "id": "drug_interaction_004",
        "category": "drug_interaction",
        "text": (
            "DRUG INTERACTION: Atorvastatin + Amlodipine. Co-administration increases "
            "Atorvastatin plasma levels by approximately 18%. While generally safe, the "
            "combination may increase risk of statin-related myopathy at high Atorvastatin "
            "doses (>40mg). Recommendation: Limit Atorvastatin to 40mg/day when combined "
            "with Amlodipine. Monitor for muscle pain, tenderness, or weakness."
        ),
    },
    {
        "id": "drug_interaction_005",
        "category": "drug_interaction",
        "text": (
            "DRUG INTERACTION: Sertraline + Aspirin/NSAIDs. SSRIs like Sertraline impair "
            "platelet aggregation. Combining with Aspirin or NSAIDs significantly increases "
            "the risk of gastrointestinal bleeding (2-3x higher). "
            "Recommendation: Consider adding a PPI (e.g., Omeprazole 20mg) for gastric "
            "protection if the combination is clinically necessary."
        ),
    },
    {
        "id": "drug_interaction_006",
        "category": "drug_interaction",
        "text": (
            "DRUG INTERACTION: Levothyroxine + Omeprazole. PPIs like Omeprazole reduce "
            "gastric acid secretion, which can impair absorption of Levothyroxine. "
            "Patients on both medications may require higher Levothyroxine doses. "
            "Recommendation: Take Levothyroxine on an empty stomach, at least 30-60 minutes "
            "before Omeprazole. Monitor TSH levels every 6-8 weeks after co-prescribing."
        ),
    },

    # ── Blood Group Safety ─────────────────────────────────────────────
    {
        "id": "blood_group_001",
        "category": "blood_safety",
        "text": (
            "BLOOD GROUP MISMATCH PROTOCOL: A blood group discrepancy across hospital "
            "records is a CRITICAL safety concern. ABO incompatibility during transfusion "
            "can cause acute hemolytic transfusion reaction (AHTR), leading to DIC, renal "
            "failure, and death. Protocol: 1) IMMEDIATELY order a type-and-screen test. "
            "2) Hold any pending transfusion orders. 3) Verify patient identity with "
            "two independent identifiers. 4) Do NOT rely on historical records alone."
        ),
    },
    {
        "id": "blood_group_002",
        "category": "blood_safety",
        "text": (
            "UNIVERSAL DONOR AND RECIPIENT: O-negative is the universal red cell donor. "
            "AB-positive is the universal plasma donor. In emergency situations where "
            "blood type is unknown or conflicting, use O-negative packed red blood cells. "
            "For plasma, use AB-positive. Never assume a patient's blood type from "
            "historical records alone when records conflict between hospitals."
        ),
    },

    # ── Dose Titration Guidelines ──────────────────────────────────────
    {
        "id": "dose_titration_001",
        "category": "dose_titration",
        "text": (
            "LISINOPRIL DOSE TITRATION: For Essential Hypertension, starting dose is "
            "typically 10mg/day. If blood pressure remains above target (>140/90 mmHg) "
            "after 2-4 weeks, titrate up to 20mg/day. Maximum dose: 40mg/day. "
            "A change from Lisinopril 10mg to 20mg across hospital records is LIKELY "
            "a legitimate dose titration, NOT a data error, especially if the patient "
            "has uncontrolled hypertension (BP > 140/90)."
        ),
    },
    {
        "id": "dose_titration_002",
        "category": "dose_titration",
        "text": (
            "METFORMIN DOSE TITRATION: For Type 2 Diabetes, starting dose is 500mg "
            "once or twice daily. Increase by 500mg every 1-2 weeks based on glycemic "
            "response. Maximum effective dose: 2000mg/day. Seeing Metformin 500mg in "
            "one hospital and 1000mg in another is LIKELY a titration step if fasting "
            "blood glucose remains > 130 mg/dL. However, seeing BOTH 500mg AND 1000mg "
            "in the same medication list may indicate a duplicate entry."
        ),
    },
    {
        "id": "dose_titration_003",
        "category": "dose_titration",
        "text": (
            "ATORVASTATIN DOSE TITRATION: For Hyperlipidemia, starting dose is 10-20mg/day. "
            "If LDL cholesterol remains above target after 4 weeks, titrate to 40mg/day. "
            "Maximum dose: 80mg/day (use with caution due to increased myopathy risk). "
            "Seeing Atorvastatin 20mg at one hospital and 40mg at another is consistent "
            "with standard statin dose escalation."
        ),
    },

    # ── Clinical Condition Guidelines ──────────────────────────────────
    {
        "id": "guideline_hypertension",
        "category": "clinical_guideline",
        "text": (
            "ESSENTIAL HYPERTENSION TREATMENT GUIDELINE (JNC-8 / AHA 2023): "
            "Target BP: <130/80 mmHg for most adults. First-line agents: "
            "ACE inhibitors (Lisinopril), ARBs (Losartan), Calcium channel blockers "
            "(Amlodipine), or Thiazide diuretics. For patients not at goal on monotherapy, "
            "combine two agents from different classes. Expected medications for a "
            "hypertension diagnosis: at least one antihypertensive agent."
        ),
    },
    {
        "id": "guideline_diabetes",
        "category": "clinical_guideline",
        "text": (
            "TYPE 2 DIABETES MANAGEMENT GUIDELINE (ADA 2024): "
            "First-line: Metformin + lifestyle modification. Target HbA1c: <7.0% for most. "
            "If fasting blood glucose > 130 mg/dL or HbA1c > 7%, consider intensifying "
            "therapy: add SGLT2 inhibitor or GLP-1 RA. Patients with T2DM should also "
            "be screened for cardiovascular risk and prescribed Aspirin 81mg if indicated."
        ),
    },
    {
        "id": "guideline_ckd",
        "category": "clinical_guideline",
        "text": (
            "CHRONIC KIDNEY DISEASE (CKD) GUIDELINE (KDIGO 2024): "
            "Stage classification by eGFR: Stage 1 (≥90), Stage 2 (60-89), Stage 3a "
            "(45-59), Stage 3b (30-44), Stage 4 (15-29), Stage 5 (<15). "
            "Key medications: ACE inhibitor or ARB for proteinuria. AVOID nephrotoxic "
            "agents: NSAIDs (Ibuprofen), aminoglycosides, iodinated contrast. "
            "Metformin: safe if eGFR ≥30, contraindicated if eGFR <30."
        ),
    },
    {
        "id": "guideline_asthma",
        "category": "clinical_guideline",
        "text": (
            "ASTHMA MANAGEMENT GUIDELINE (GINA 2024): "
            "Step 1: As-needed low-dose ICS-formoterol (preferred) or SABA (Albuterol). "
            "Step 2: Daily low-dose ICS + as-needed SABA. "
            "Step 3: Low-dose ICS-LABA. Step 4: Medium-dose ICS-LABA. "
            "Expected medication for asthma diagnosis: Albuterol inhaler (rescue) and/or "
            "an ICS (maintenance). A patient diagnosed with asthma but only on Albuterol "
            "may have mild intermittent asthma — not necessarily incomplete treatment."
        ),
    },
    {
        "id": "guideline_depression",
        "category": "clinical_guideline",
        "text": (
            "MAJOR DEPRESSIVE DISORDER GUIDELINE (APA 2023): "
            "First-line pharmacotherapy: SSRIs (Sertraline, Escitalopram) or SNRIs "
            "(Venlafaxine, Duloxetine). Sertraline 50mg is a standard starting dose. "
            "If inadequate response after 4-6 weeks, increase to 100mg or switch agents. "
            "Expected medication for MDD diagnosis: at least one antidepressant."
        ),
    },
    {
        "id": "guideline_gerd",
        "category": "clinical_guideline",
        "text": (
            "GERD TREATMENT GUIDELINE (ACG 2022): "
            "First-line: PPI therapy (Omeprazole 20mg once daily) for 8 weeks. "
            "If symptoms persist, increase to twice daily. Long-term PPI use: monitor "
            "for B12 deficiency, hypomagnesemia, and osteoporosis risk. "
            "Expected medication for GERD diagnosis: Omeprazole or equivalent PPI."
        ),
    },

    # ── Allergy Cross-Reactivity ───────────────────────────────────────
    {
        "id": "allergy_001",
        "category": "allergy",
        "text": (
            "ASPIRIN ALLERGY & NSAID CROSS-REACTIVITY: Patients with true Aspirin allergy "
            "(urticaria, angioedema, or anaphylaxis) have a 20-25% cross-reactivity rate "
            "with other NSAIDs (Ibuprofen, Naproxen). If a patient has a documented "
            "Aspirin allergy, prescribing Ibuprofen is a HIGH-RISK decision. "
            "Recommendation: Use Acetaminophen as the alternative analgesic. "
            "If NSAID is essential, refer for desensitization protocol."
        ),
    },
    {
        "id": "allergy_002",
        "category": "allergy",
        "text": (
            "PENICILLIN ALLERGY: Approximately 10% of patients report Penicillin allergy, "
            "but >90% are NOT truly allergic upon testing. Cross-reactivity with "
            "cephalosporins is ~1-2% (not 10% as historically reported). "
            "If an allergy discrepancy exists between hospitals, recommend allergy skin "
            "testing to confirm or rule out true Penicillin allergy."
        ),
    },
    {
        "id": "allergy_003",
        "category": "allergy",
        "text": (
            "SULFA DRUG ALLERGY: Allergic reactions to sulfonamide antibiotics "
            "(Sulfamethoxazole/Trimethoprim) do NOT reliably predict cross-reactivity "
            "with non-antibiotic sulfonamides (Furosemide, Thiazides, Celecoxib). "
            "The cross-reactivity myth is based on a shared sulfonamide moiety, "
            "but the antigenic determinants differ. However, exercise caution in patients "
            "with severe sulfa antibiotic reactions (SJS/TEN)."
        ),
    },
]


# ---------------------------------------------------------------------------
# Seed the Knowledge Base
# ---------------------------------------------------------------------------

def seed_knowledge_base(force: bool = False) -> int:
    """
    Insert all curated medical knowledge documents into ChromaDB.
    Returns the number of documents added.
    Skips if the collection already has documents (unless force=True).
    """
    collection = _get_collection()

    if collection.count() > 0 and not force:
        logger.info("RAG knowledge base already seeded (%d documents). Skipping.", collection.count())
        return 0

    if force:
        # Clear existing documents
        existing = collection.get()
        if existing["ids"]:
            collection.delete(ids=existing["ids"])

    ids = []
    documents = []
    metadatas = []

    for doc in MEDICAL_KNOWLEDGE_DOCS:
        ids.append(doc["id"])
        documents.append(doc["text"])
        metadatas.append({"category": doc["category"]})

    collection.add(ids=ids, documents=documents, metadatas=metadatas)

    logger.info("RAG knowledge base seeded with %d medical reference documents.", len(ids))
    return len(ids)


# ---------------------------------------------------------------------------
# Query the Knowledge Base
# ---------------------------------------------------------------------------

def query_knowledge_base(
    query: str,
    n_results: int = 3,
    category_filter: str = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve the most relevant medical knowledge documents for a query.

    Args:
        query: The search query (e.g., patient meds, diagnoses, doctor's question)
        n_results: Number of results to return
        category_filter: Optional filter by category (drug_interaction, blood_safety, etc.)

    Returns:
        List of dicts with 'text', 'category', 'distance' keys
    """
    collection = _get_collection()

    if collection.count() == 0:
        logger.warning("RAG knowledge base is empty. Run seed_knowledge_base() first.")
        return []

    where_filter = None
    if category_filter:
        where_filter = {"category": category_filter}

    results = collection.query(
        query_texts=[query],
        n_results=min(n_results, collection.count()),
        where=where_filter,
    )

    docs = []
    for i in range(len(results["ids"][0])):
        docs.append({
            "id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "category": results["metadatas"][0][i].get("category", ""),
            "distance": results["distances"][0][i] if results.get("distances") else None,
        })

    return docs


def build_rag_context(
    patient_data: Dict[str, Any],
    doctor_message: str,
) -> str:
    """
    Build a RAG-augmented context string for Nurse Joy.

    Combines:
    1. The doctor's question
    2. The patient's medications/diagnoses (for relevance matching)
    3. Retrieved medical knowledge documents

    Returns a formatted string to inject into the LLM system prompt.
    """
    # Build a composite query from the doctor's message + patient clinical data
    medications = patient_data.get("medications", [])
    diagnoses = patient_data.get("diagnosis", [])
    allergies = patient_data.get("allergies", [])

    query_parts = [doctor_message]
    if medications:
        query_parts.append(f"Patient medications: {', '.join(medications)}")
    if diagnoses:
        query_parts.append(f"Patient diagnoses: {', '.join(diagnoses)}")
    if allergies:
        query_parts.append(f"Patient allergies: {', '.join(allergies)}")

    composite_query = " | ".join(query_parts)

    # Retrieve relevant documents
    results = query_knowledge_base(composite_query, n_results=3)

    if not results:
        return ""

    # Format as context block
    lines = ["MEDICAL REFERENCE KNOWLEDGE (from HealthSync RAG Database):"]
    for i, doc in enumerate(results, 1):
        # Only include if reasonably relevant (cosine distance < 1.2)
        if doc.get("distance") is not None and doc["distance"] > 1.2:
            continue
        lines.append(f"  Reference {i} [{doc['category']}]: {doc['text']}")

    if len(lines) == 1:
        return ""  # No relevant docs found

    return "\n".join(lines) + "\n"
