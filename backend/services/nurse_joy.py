"""
Nurse Joy - Ultra-fast Context-Aware Chatbot Engine + RAG
=========================================================
Now powered by Retrieval-Augmented Generation (RAG) using ChromaDB.
Nurse Joy cross-references patient data against a curated medical
knowledge base to provide evidence-based clinical insights.
"""

import json
import logging
import urllib.request
import urllib.error
import httpx
from typing import Dict, Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared Prompt Builder (used by both sync and streaming paths)
# ---------------------------------------------------------------------------

def _build_system_prompt(
    patient: Dict[str, Any],
    conflicts: list,
    rag_context: str = "",
) -> str:
    """Build the Nurse Joy system prompt with optional RAG context."""
    system_prompt = (
        "You are Nurse Joy, a friendly, professional, and ultra-fast AI clinical assistant for the HealthSync platform. "
        "Your job is to answer the Doctor's questions clearly and concisely based ONLY on the provided context.\n\n"
    )
    

    if patient:
        name = patient.get("name", "Unknown Patient")
        system_prompt += f"CURRENT PATIENT: {name}\n"
        system_prompt += f"GENDER: {patient.get('gender', 'Unknown')}\n"
        system_prompt += f"BLOOD GROUP: {patient.get('blood_group', 'Unknown')}\n"
        system_prompt += f"ALLERGIES: {', '.join(patient.get('allergies', [])) or 'None'}\n"
        system_prompt += f"DIAGNOSES: {', '.join(patient.get('diagnosis', [])) or 'None'}\n"
        system_prompt += f"MEDICATIONS: {', '.join(patient.get('medications', [])) or 'None'}\n\n"

        if conflicts:
            system_prompt += "DATA CONFLICTS RESOLVED (from cross-hospital EHRs):\n"
            for c in conflicts:
                system_prompt += f"- Type: {c.get('conflict_type')} | Resolved via: {c.get('resolution_rule')} | Details: {json.dumps(c.get('values', {}))}\n"
            system_prompt += "\n"
    else:
        system_prompt += (
            "You are currently in Global Mode on the dashboard. There is no specific patient selected. "
            "Help the Doctor navigate the HealthSync platform. HealthSync automatically intercepts walk-in patients, "
            "audits them against their central PostgreSQL EHR using Cooperative AI Agents, and resolves clinical conflicts."
        )

    # Inject RAG context (retrieved medical knowledge)
    if rag_context:
        system_prompt += "\n" + rag_context + "\n"
        system_prompt += (
            "IMPORTANT: When your answer references the medical knowledge above, "
            "briefly cite the source (e.g., 'per ADA 2024 guidelines' or "
            "'drug interaction alert'). This helps the Doctor trust your reasoning.\n\n"
        )

    return system_prompt


def _get_rag_context(message: str, patient: Dict[str, Any]) -> str:
    """Safely retrieve RAG context. Returns empty string on failure."""
    try:
        from services.rag_knowledge import build_rag_context
        return build_rag_context(patient, message)
    except Exception as e:
        logger.warning("RAG retrieval failed (non-fatal): %s", e)
        return ""


# ---------------------------------------------------------------------------
# Synchronous Response (original HTTP endpoint)
# ---------------------------------------------------------------------------

def generate_joy_response(message: str, patient_context: Dict[str, Any]) -> str:
    """
    Connects to the local Ollama instance to generate a context-aware response.
    Now augmented with RAG medical knowledge retrieval.
    Falls back to a basic generic message if Ollama is unreachable.
    """
    patient = patient_context.get("patient", {})
    conflicts = patient_context.get("conflicts", [])

    # Retrieve relevant medical knowledge via RAG
    rag_context = _get_rag_context(message, patient)

    system_prompt = _build_system_prompt(patient, conflicts, rag_context)

    # Prepare Ollama Payload
    payload = {
        "model": "llama2:latest",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ],
        "stream": False
    }

    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/chat",
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('message', {}).get('content', "I'm sorry, I couldn't formulate a response.")

    except Exception as e:
        # Fallback if Ollama is off or errors out
        return f"I'm sorry Doctor, my connection to the local LLM brain (Ollama) failed: {str(e)}. Please ensure Ollama is running `llama2`."


# ---------------------------------------------------------------------------
# Streaming Response (WebSocket endpoint)
# ---------------------------------------------------------------------------

async def stream_joy_response(message: str, patient_context: Dict[str, Any]):
    """
    Async generator that connects to the local Ollama instance and yields response tokens.
    Now augmented with RAG medical knowledge retrieval.
    """
    patient = patient_context.get("patient", {})
    conflicts = patient_context.get("conflicts", [])

    # Retrieve relevant medical knowledge via RAG
    rag_context = _get_rag_context(message, patient)

    system_prompt = _build_system_prompt(patient, conflicts, rag_context)

    # Prepare Ollama Payload
    payload = {
        "model": "llama2:latest",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ],
        "stream": True
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", "http://localhost:11434/api/chat", json=payload) as response:
                async for chunk in response.aiter_lines():
                    if chunk:
                        data = json.loads(chunk)
                        yield data.get("message", {}).get("content", "")
    except Exception as e:
        yield f" [Error connecting to Ollama: {str(e)}]"
