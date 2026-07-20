"""
Clinical AI Agents Orchestration — 3 Cooperative CrewAI Agents + Ollama

Three genuinely cooperative agents, each performing distinct clinical reasoning:

Pipeline:
  Agent 1 — Ingestion Validator:
      Reasons about whether the incoming report is clinically plausible.
      Does the medication list make sense for the diagnoses?
      Are there obvious data quality red flags?

  Agent 2 — Conflict Auditor:
      Rules engine detects field mismatches (deterministic, fast).
      LLM reasons about medication dosage context:
      "Is Lisinopril 10mg→20mg a titration or a data error?"

  Agent 3 — Clinical Chief:
      Receives Agent 1 + Agent 2 outputs.
      Synthesizes final action items weighing upstream context.
      If Agent 1 flagged the report as suspicious, recommendations
      are more cautious. If Agent 2 said "likely titration", the Chief
      doesn't suggest re-testing the dose.
"""

import json
import re
import logging
from typing import Dict, List, Any
from datetime import datetime, timezone

from crewai import Agent, Task, Crew, Process, LLM

from database.models import PatientRecord, ConflictRecord
from services.department_mapper import map_conflict_to_department, get_confidence_score

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Local LLM Configuration (Ollama)
# ---------------------------------------------------------------------------

def _get_ollama_llm():
    """Initialize the local Ollama LLM for CrewAI agents."""
    return LLM(
        model="ollama/llama3",
        base_url="http://localhost:11434",
        temperature=0.3,
    )


# ---------------------------------------------------------------------------
# Output Cleaner — strips markdown artifacts from LLM output
# ---------------------------------------------------------------------------

def _clean_llm_output(raw_text: str) -> str:
    """
    Post-process LLM output:
    - Strip markdown bold/italic markers (**, *, ##)
    - Remove excessive blank lines
    - Trim verbose preamble sentences
    - Keep only actionable content
    """
    text = str(raw_text)

    # Strip markdown formatting
    text = re.sub(r'\*\*', '', text)       # Remove **bold**
    text = re.sub(r'\*', '•', text)        # Convert * bullets to •
    text = re.sub(r'#{1,4}\s*', '', text)  # Remove ### headings
    text = re.sub(r'`', '', text)          # Remove backticks

    # Remove common LLM preamble filler
    filler_patterns = [
        r'(?i)^(here (is|are) (my|the|a) (recommendation|analysis|summary|response|answer)[:\.]?\s*)',
        r'(?i)^(based on (my|the) (analysis|review|assessment)[,\.]?\s*)',
        r'(?i)^(as (a|the) (chief|senior|clinical) (medical|physician|officer|advisor)[,\.]?\s*)',
        r'(?i)^(after (careful|thorough) (review|analysis|examination)[,\.]?\s*)',
        r'(?i)^(i have (reviewed|analyzed|examined) the (data|records|report)[,\.]?\s*)',
    ]
    for pattern in filler_patterns:
        text = re.sub(pattern, '', text, flags=re.MULTILINE)

    # Collapse multiple newlines
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Trim leading/trailing whitespace
    text = text.strip()

    return text


# ---------------------------------------------------------------------------
# Rule-based Conflict Detection (Fast, deterministic)
# ---------------------------------------------------------------------------

def _detect_conflicts_rule_based(
    incoming: Dict[str, Any], history: List[PatientRecord]
) -> List[Dict[str, Any]]:
    """
    Deterministic conflict detection using field comparison.
    Identifies WHAT the conflicts are before the LLM reasons about them.
    """
    conflicts = []

    if not history:
        return conflicts

    # 1. Blood Group Mismatch
    blood_mismatches = {}
    for hist in history:
        if hist.blood_group and hist.blood_group != incoming.get("blood_group"):
            blood_mismatches[hist.source_hospital] = hist.blood_group

    if blood_mismatches:
        blood_mismatches[incoming.get("source_hospital", "Incoming")] = incoming.get("blood_group")
        conflicts.append({
            "field": "blood_group",
            "conflict_type": "Blood Group Mismatch",
            "values": blood_mismatches,
        })

    # 2. Diagnosis Mismatch
    hist_dxs = set()
    for hist in history:
        try:
            hist_dxs.update(json.loads(hist.diagnosis))
        except Exception:
            pass

    new_dxs = set(incoming.get("diagnosis", []))
    if hist_dxs and new_dxs and hist_dxs != new_dxs:
        diag_mapping = {}
        for hist in history:
            try:
                diag_mapping[hist.source_hospital] = json.loads(hist.diagnosis)
            except Exception:
                diag_mapping[hist.source_hospital] = []
        diag_mapping[incoming.get("source_hospital", "Incoming")] = incoming.get("diagnosis", [])
        conflicts.append({
            "field": "diagnosis",
            "conflict_type": "Diagnosis Mismatch",
            "values": diag_mapping,
        })

    # 3. Medications Mismatch
    hist_meds = set()
    for hist in history:
        try:
            hist_meds.update(json.loads(hist.medications))
        except Exception:
            pass

    new_meds = set(incoming.get("medications", []))
    if hist_meds and new_meds and hist_meds != new_meds:
        med_mapping = {}
        for hist in history:
            try:
                med_mapping[hist.source_hospital] = json.loads(hist.medications)
            except Exception:
                med_mapping[hist.source_hospital] = []
        med_mapping[incoming.get("source_hospital", "Incoming")] = incoming.get("medications", [])
        conflicts.append({
            "field": "medications",
            "conflict_type": "Medication Mismatch",
            "values": med_mapping,
        })

    # 4. Medication Dosage Mismatch (same drug, different strength)
    dose_conflicts = _detect_dose_conflicts(incoming, history)
    conflicts.extend(dose_conflicts)

    return conflicts


def _parse_med(med_str: str):
    """Parse 'Lisinopril 10mg' -> ('lisinopril', '10mg')."""
    match = re.match(
        r'^(.+?)\s+(\d+\s*(?:mg|mcg|ml|units?|iu|g))\s*$',
        med_str.strip(), re.IGNORECASE,
    )
    if match:
        return match.group(1).strip().lower(), match.group(2).strip().lower()
    return med_str.strip().lower(), ""


def _detect_dose_conflicts(
    incoming: Dict[str, Any], history: List[PatientRecord]
) -> List[Dict[str, Any]]:
    """Detect same-drug-different-dose conflicts between incoming and history."""
    conflicts = []

    # Build incoming drug->strength map
    incoming_drugs = {}
    for med in incoming.get("medications", []):
        base, strength = _parse_med(med)
        if strength:
            incoming_drugs[base] = strength

    # Build history drug->strength maps
    for hist in history:
        try:
            hist_meds = json.loads(hist.medications)
        except Exception:
            continue

        hist_drugs = {}
        for med in hist_meds:
            base, strength = _parse_med(med)
            if strength:
                hist_drugs[base] = strength

        # Check for same drug with different dose
        for drug_name, incoming_dose in incoming_drugs.items():
            if drug_name in hist_drugs and hist_drugs[drug_name] != incoming_dose:
                conflicts.append({
                    "field": "medication_dosage",
                    "conflict_type": "Medication Dosage Mismatch",
                    "values": {
                        hist.source_hospital: f"{drug_name.title()} {hist_drugs[drug_name]}",
                        incoming.get("source_hospital", "Incoming"): f"{drug_name.title()} {incoming_dose}",
                    },
                    "drug_name": drug_name.title(),
                    "dose_old": hist_drugs[drug_name],
                    "dose_new": incoming_dose,
                })

    return conflicts


# ---------------------------------------------------------------------------
# CrewAI Agent Definitions — 3 Real Cooperative Agents
# ---------------------------------------------------------------------------

def _build_ingestion_validator(llm):
    """Agent 1: Reasons about incoming report quality and plausibility."""
    return Agent(
        role="Clinical Ingestion Validator",
        goal=(
            "Assess whether an incoming patient report is clinically plausible. "
            "Check if the medication list makes sense for the listed diagnoses. "
            "Flag any obvious data quality issues."
        ),
        backstory=(
            "You are a senior clinical data quality specialist. You review "
            "incoming patient reports for plausibility before they enter the "
            "hospital system. You check whether prescribed medications match "
            "the listed diagnoses, and flag suspicious combinations. "
            "You respond with a brief structured assessment."
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )


def _build_conflict_auditor(llm):
    """Agent 2: Reasons about clinical context of detected conflicts."""
    return Agent(
        role="Conflict Auditor Analyst",
        goal=(
            "For each detected data conflict, determine whether it is likely "
            "a legitimate clinical change (e.g., dose titration for an "
            "uncontrolled condition) or a data entry error. Provide brief "
            "clinical reasoning for each."
        ),
        backstory=(
            "You are a clinical pharmacist and data auditor. When a medication "
            "dosage differs between hospital records, you reason about WHY. "
            "A change from Lisinopril 10mg to 20mg in a hypertensive patient "
            "is probably a legitimate dose escalation. But Metformin appearing "
            "at both 500mg and 1000mg in the same visit is likely a duplicate. "
            "You give a brief assessment per conflict."
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )


def _build_clinical_chief(llm):
    """Agent 3: Synthesizes Agent 1 + Agent 2 outputs into final recommendations."""
    return Agent(
        role="Chief Medical Decision Advisor",
        goal=(
            "Synthesize the Ingestion Validator's quality assessment and the "
            "Conflict Auditor's per-conflict reasoning into final, actionable "
            "clinical recommendations for the attending physician."
        ),
        backstory=(
            "You are a senior chief medical officer. You receive two upstream "
            "analyses: (1) a report quality assessment and (2) per-conflict "
            "clinical reasoning. You weigh both to produce final action items. "
            "If the report quality is poor, your recommendations are more "
            "cautious. If the auditor identified a likely dose titration, "
            "you don't recommend re-testing that drug. You are concise and "
            "action-oriented. Never repeat data back. Only state what the "
            "doctor should DO."
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )


# ---------------------------------------------------------------------------
# Task Builders
# ---------------------------------------------------------------------------

def _build_validation_task(agent, incoming_report):
    """Task for Agent 1: Assess incoming report plausibility."""
    diagnoses = incoming_report.get("diagnosis", [])
    medications = incoming_report.get("medications", [])
    gender = incoming_report.get("gender", "Unknown")

    return Task(
        description=(
            f"Patient: {incoming_report.get('name')}\n"
            f"Gender: {gender}\n"
            f"Diagnoses: {', '.join(diagnoses) if diagnoses else 'None listed'}\n"
            f"Medications: {', '.join(medications) if medications else 'None listed'}\n\n"
            f"Assess this report's clinical plausibility:\n"
            f"1. Do the medications match the diagnoses? "
            f"(e.g., is there an antihypertensive for a hypertension diagnosis?)\n"
            f"2. Are any medications missing that you'd expect for these diagnoses?\n"
            f"3. Are there any red flags (wrong drug for condition, suspicious combo)?\n\n"
            f"Respond with EXACTLY this format:\n"
            f"QUALITY: [GOOD / SUSPICIOUS / INCOMPLETE]\n"
            f"FLAGS: [bullet list of issues, or 'None']\n"
            f"NOTES: [one sentence summary]\n\n"
            f"Keep total response UNDER 80 words. No markdown."
        ),
        expected_output=(
            "A structured assessment with QUALITY, FLAGS, and NOTES fields."
        ),
        agent=agent,
    )


def _build_auditor_task(agent, conflicts, incoming_report, history_summary):
    """Task for Agent 2: Reason about each conflict's clinical context."""
    # Format conflicts compactly
    conflict_lines = []
    for i, c in enumerate(conflicts, 1):
        vals = ", ".join(f"{k}: {v}" for k, v in c["values"].items())
        conflict_lines.append(f"{i}. {c['conflict_type']} — {vals}")
    conflict_block = "\n".join(conflict_lines) if conflict_lines else "No conflicts detected."

    diagnoses = incoming_report.get("diagnosis", [])

    return Task(
        description=(
            f"Patient: {incoming_report.get('name')}\n"
            f"Diagnoses: {', '.join(diagnoses)}\n\n"
            f"DETECTED CONFLICTS:\n{conflict_block}\n\n"
            f"EXISTING RECORDS:\n{history_summary}\n\n"
            f"For EACH conflict, provide a brief clinical assessment:\n"
            f"- Is this likely a legitimate clinical change or a data error?\n"
            f"- For dose differences: is this a probable dose titration "
            f"for an uncontrolled condition?\n\n"
            f"Format each as:\n"
            f"CONFLICT [number]: [LIKELY TITRATION / LIKELY ERROR / NEEDS VERIFICATION]\n"
            f"REASONING: [one sentence]\n\n"
            f"Keep total response UNDER 100 words. No markdown."
        ),
        expected_output=(
            "Per-conflict assessments with clinical reasoning."
        ),
        agent=agent,
    )


def _build_chief_task(agent, validation_result, auditor_result, conflicts):
    """Task for Agent 3: Synthesize upstream agent outputs into final recommendations."""
    conflict_summary = []
    for i, c in enumerate(conflicts, 1):
        conflict_summary.append(f"{i}. {c['conflict_type']}")

    return Task(
        description=(
            f"UPSTREAM AGENT OUTPUTS:\n\n"
            f"--- Ingestion Validator Assessment ---\n"
            f"{validation_result}\n\n"
            f"--- Conflict Auditor Reasoning ---\n"
            f"{auditor_result}\n\n"
            f"CONFLICTS: {', '.join(conflict_summary)}\n\n"
            f"Synthesize both assessments into FINAL action items.\n"
            f"For EACH conflict write exactly:\n"
            f"- Action: what test or step to take\n"
            f"- Urgency: IMMEDIATE / SOON / ROUTINE\n"
            f"- Risk: one sentence on clinical danger\n\n"
            f"RULES:\n"
            f"- If the Validator flagged report quality issues, be MORE cautious.\n"
            f"- If the Auditor said 'likely titration', do NOT recommend re-testing "
            f"that drug — instead recommend confirming with the patient.\n"
            f"- Do NOT repeat data back. Only state what to DO.\n"
            f"- Keep total response UNDER 120 words. No markdown."
        ),
        expected_output=(
            "Final concise action items with Action, Urgency, and Risk per conflict."
        ),
        agent=agent,
    )


# ---------------------------------------------------------------------------
# Main Orchestrator Class
# ---------------------------------------------------------------------------

class ClinicalAIOrchestrator:
    """
    Orchestrates clinical admission audits with 3 cooperative agents:
    1. Ingestion Validator — assesses report plausibility (LLM)
    2. Conflict Auditor — rules detect conflicts + LLM reasons about context (LLM)
    3. Clinical Chief — synthesizes Agent 1 + Agent 2 into final recommendations (LLM)
    """

    def __init__(self):
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            self._llm = _get_ollama_llm()
        return self._llm

    def process_incoming_admission(
        self, raw_report: Dict[str, Any], history: List[PatientRecord]
    ) -> Dict[str, Any]:
        """
        Run the full 3-agent cooperative pipeline.

        Returns a dict with:
            - conflicts: list of detected conflicts
            - conflict_records: list of ConflictRecord DB objects
            - agent_1_assessment: Ingestion Validator output
            - agent_2_reasoning: Conflict Auditor output
            - agent_3_recommendations: Clinical Chief output
        """

        # Step 1: Deterministic conflict detection (fast, no LLM)
        conflicts = _detect_conflicts_rule_based(raw_report, history)

        # Build history summary for agents
        history_summary = ""
        for h in history:
            try:
                dx = json.loads(h.diagnosis)
            except Exception:
                dx = []
            try:
                meds = json.loads(h.medications)
            except Exception:
                meds = []
            history_summary += (
                f"  {h.source_hospital}: Blood={h.blood_group}, "
                f"Dx={dx}, Meds={meds}\n"
            )
        if not history_summary:
            history_summary = "  No prior records found."

        # Default outputs (used if LLM is unavailable)
        agent_1_output = self._fallback_validation(raw_report)
        agent_2_output = self._fallback_auditor(conflicts)
        agent_3_output = self._fallback_recommendation(conflicts)

        # Step 2: Run 3-agent cooperative pipeline via CrewAI
        try:
            llm = self._get_llm()

            # Build agents
            validator = _build_ingestion_validator(llm)
            auditor = _build_conflict_auditor(llm)
            chief = _build_clinical_chief(llm)

            # Build tasks (chained: each receives upstream output)
            task_1 = _build_validation_task(validator, raw_report)
            task_2 = _build_auditor_task(auditor, conflicts, raw_report, history_summary)

            # Run Agent 1 + Agent 2 first
            crew_phase1 = Crew(
                agents=[validator, auditor],
                tasks=[task_1, task_2],
                process=Process.sequential,
                verbose=False,
            )

            logger.info(
                "CrewAI Phase 1: Running Validator + Auditor for '%s' (%d conflicts)",
                raw_report.get("name"), len(conflicts),
            )
            phase1_result = crew_phase1.kickoff()

            # Extract per-task outputs
            agent_1_output = _clean_llm_output(str(phase1_result.tasks_output[0]))
            agent_2_output = _clean_llm_output(str(phase1_result.tasks_output[1]))

            # Run Agent 3 with upstream context
            task_3 = _build_chief_task(chief, agent_1_output, agent_2_output, conflicts)

            crew_phase2 = Crew(
                agents=[chief],
                tasks=[task_3],
                process=Process.sequential,
                verbose=False,
            )

            logger.info("CrewAI Phase 2: Running Clinical Chief for '%s'", raw_report.get("name"))
            phase2_result = crew_phase2.kickoff()
            agent_3_output = _clean_llm_output(str(phase2_result))

            logger.info("CrewAI: Full 3-agent audit complete for '%s'", raw_report.get("name"))

        except Exception as e:
            logger.error("CrewAI cooperative pipeline failed, using fallback: %s", e)
            # Fallback outputs are already set above

        # Step 3: Package as ConflictRecord objects for DB storage
        conflict_records = []
        for conflict in conflicts:
            hospitals_involved = list(conflict["values"].keys())
            confidence = get_confidence_score(hospitals_involved)
            department = map_conflict_to_department(
                conflict["field"],
                list(conflict["values"].values())
            )

            record = ConflictRecord(
                patient_id=raw_report.get("patient_id", ""),
                patient_name=raw_report.get("name", ""),
                conflict_type=conflict["conflict_type"],
                hospitals=json.dumps(hospitals_involved),
                values=json.dumps(conflict["values"]),
                department=department,
                confidence_score=round(confidence, 2),
                recommendation=agent_3_output,
                is_reviewed=False,
            )
            conflict_records.append(record)

        return {
            "conflicts": conflicts,
            "conflict_records": conflict_records,
            "agent_1_assessment": agent_1_output,
            "agent_2_reasoning": agent_2_output,
            "agent_3_recommendations": agent_3_output,
        }

    # ------------------------------------------------------------------
    # Fallback templates (used when Ollama is offline)
    # ------------------------------------------------------------------

    def _fallback_validation(self, raw_report: Dict[str, Any]) -> str:
        """Template fallback for Agent 1."""
        diagnoses = raw_report.get("diagnosis", [])
        medications = raw_report.get("medications", [])

        if not diagnoses and not medications:
            return "QUALITY: INCOMPLETE\nFLAGS: No diagnoses or medications listed\nNOTES: Report lacks core clinical data."
        if not medications and diagnoses:
            return (
                f"QUALITY: SUSPICIOUS\n"
                f"FLAGS: Patient has {len(diagnoses)} diagnosis(es) but no medications listed\n"
                f"NOTES: Expected at least one prescribed medication for active conditions."
            )
        return (
            f"QUALITY: GOOD\n"
            f"FLAGS: None\n"
            f"NOTES: Report contains {len(diagnoses)} diagnosis(es) and {len(medications)} medication(s). "
            f"Automated validation passed (LLM unavailable for deeper analysis)."
        )

    def _fallback_auditor(self, conflicts: List[Dict]) -> str:
        """Template fallback for Agent 2."""
        if not conflicts:
            return "No conflicts detected. All records are consistent."

        parts = []
        for i, c in enumerate(conflicts, 1):
            field = c["field"]
            if field == "medication_dosage":
                parts.append(
                    f"CONFLICT {i}: NEEDS VERIFICATION\n"
                    f"REASONING: Medication dosage difference detected. "
                    f"Cannot determine if this is a dose titration or data error "
                    f"without LLM analysis. Recommend manual pharmacist review."
                )
            elif field == "blood_group":
                parts.append(
                    f"CONFLICT {i}: LIKELY ERROR\n"
                    f"REASONING: Blood group should not change between visits. "
                    f"This is almost certainly a data entry error or sample mix-up."
                )
            elif field == "medications":
                parts.append(
                    f"CONFLICT {i}: NEEDS VERIFICATION\n"
                    f"REASONING: Medication list differences may reflect prescribing "
                    f"changes or recording gaps. Pharmacist reconciliation needed."
                )
            elif field == "diagnosis":
                parts.append(
                    f"CONFLICT {i}: NEEDS VERIFICATION\n"
                    f"REASONING: Diagnosis differences may reflect evolving conditions "
                    f"or coding discrepancies. Clinical review required."
                )
            else:
                parts.append(
                    f"CONFLICT {i}: NEEDS VERIFICATION\n"
                    f"REASONING: Field '{field}' differs across sources."
                )
        return "\n\n".join(parts)

    def _fallback_recommendation(self, conflicts: List[Dict]) -> str:
        """Template fallback for Agent 3."""
        if not conflicts:
            return "No conflicts detected. Record is clean and ready for sign-off."

        parts = []
        for c in conflicts:
            field = c["field"]
            if field == "blood_group":
                parts.append(
                    "Action: Order ABO/Rh blood typing test\n"
                    "Urgency: IMMEDIATE\n"
                    "Risk: Blood group mismatch is life-threatening during transfusion"
                )
            elif field == "diagnosis":
                parts.append(
                    "Action: Schedule clinical review to reconcile diagnoses\n"
                    "Urgency: SOON\n"
                    "Risk: Incorrect diagnosis may lead to wrong treatment plan"
                )
            elif field == "medications":
                parts.append(
                    "Action: Perform medication reconciliation with patient\n"
                    "Urgency: SOON\n"
                    "Risk: Incorrect medications may cause adverse drug interactions"
                )
            elif field == "medication_dosage":
                parts.append(
                    "Action: Confirm current dose with patient and prescribing physician\n"
                    "Urgency: SOON\n"
                    "Risk: Wrong dosage may cause under-treatment or adverse effects"
                )
        return "\n\n".join(parts) if parts else "No action required."
