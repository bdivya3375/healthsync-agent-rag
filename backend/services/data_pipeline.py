"""
Data Pipeline — Unified Ingestion Service

Scans the data directory for hospital files (JSON, XML, CSV),
routes each file to its appropriate parser, and returns a
consolidated list of FHIR-aligned Patient objects.

Designed for production use with:
    - Proper error handling per file (one bad file won't crash the pipeline)
    - Structured logging for observability
    - Path-safe resolution (works regardless of cwd)
    - Summary statistics for monitoring
"""

import os
import logging
from typing import List, Dict

from services.json_parser import parse_json
from services.xml_parser import parse_xml
from services.csv_parser import parse_csv
from models.unified_schema import Patient

# Configure module-level logger
logger = logging.getLogger(__name__)

# Map file extensions to their parser functions
PARSER_REGISTRY = {
    ".json": parse_json,
    ".xml": parse_xml,
    ".csv": parse_csv,
}

# Files to skip during ingestion (not patient data)
SKIP_FILES = {"conflict_manifest.json"}


def _resolve_data_dir(custom_path: str = None) -> str:
    """
    Resolve the absolute path to the data directory.

    Falls back to `backend/data/` relative to this file's location
    if no custom path is provided.
    """
    if custom_path:
        resolved = os.path.abspath(custom_path)
    else:
        resolved = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "data")
        )

    if not os.path.isdir(resolved):
        raise FileNotFoundError(f"Data directory not found: {resolved}")

    return resolved


def process_all_data(data_dir: str = None) -> List[Patient]:
    """
    Ingest all hospital data files and return unified Patient records.

    Args:
        data_dir: Optional custom path to the data directory.
                  Defaults to `backend/data/` relative to this module.

    Returns:
        List of unified Patient objects from all successfully parsed files.

    Raises:
        FileNotFoundError: If the data directory does not exist.
    """
    data_path = _resolve_data_dir(data_dir)
    all_patients: List[Patient] = []
    stats: Dict[str, int] = {}  # filename → patient count
    errors: List[str] = []

    logger.info("Starting data ingestion from: %s", data_path)

    # Scan data directory for supported files
    for filename in sorted(os.listdir(data_path)):
        # Skip non-patient files
        if filename in SKIP_FILES:
            logger.debug("Skipping non-patient file: %s", filename)
            continue

        file_path = os.path.join(data_path, filename)

        # Skip directories (if any exist in future)
        if os.path.isdir(file_path):
            logger.debug("Skipping directory: %s", filename)
            continue

        # Determine file extension and find matching parser
        _, ext = os.path.splitext(filename)
        ext = ext.lower()

        parser = PARSER_REGISTRY.get(ext)
        if parser is None:
            logger.warning("No parser registered for extension '%s': %s", ext, filename)
            continue

        # Parse the file with error isolation
        try:
            patients = parser(file_path)
            all_patients.extend(patients)
            stats[filename] = len(patients)
            logger.info(
                "Parsed %s: %d patients ingested", filename, len(patients)
            )
        except Exception as e:
            error_msg = f"Failed to parse {filename}: {type(e).__name__}: {e}"
            errors.append(error_msg)
            logger.error(error_msg, exc_info=True)

    # Log summary
    total = len(all_patients)
    logger.info("=" * 50)
    logger.info("DATA INGESTION COMPLETE")
    logger.info("Total patients ingested: %d", total)
    for fname, count in stats.items():
        logger.info("  %s: %d patients", fname, count)
    if errors:
        logger.warning("Errors encountered: %d files failed", len(errors))
        for err in errors:
            logger.warning("  %s", err)
    logger.info("=" * 50)

    return all_patients


def get_ingestion_summary(data_dir: str = None) -> Dict:
    """
    Run ingestion and return a structured summary dict.

    Useful for API endpoints or health checks that need
    machine-readable ingestion results.
    """
    data_path = _resolve_data_dir(data_dir)
    summary = {
        "data_directory": data_path,
        "files_found": 0,
        "files_parsed": 0,
        "files_skipped": 0,
        "files_failed": 0,
        "total_patients": 0,
        "per_file": {},
        "errors": [],
    }

    for filename in sorted(os.listdir(data_path)):
        if filename in SKIP_FILES or os.path.isdir(os.path.join(data_path, filename)):
            summary["files_skipped"] += 1
            continue

        _, ext = os.path.splitext(filename)
        parser = PARSER_REGISTRY.get(ext.lower())

        if parser is None:
            summary["files_skipped"] += 1
            continue

        summary["files_found"] += 1
        file_path = os.path.join(data_path, filename)

        try:
            patients = parser(file_path)
            count = len(patients)
            summary["files_parsed"] += 1
            summary["total_patients"] += count
            summary["per_file"][filename] = {
                "status": "success",
                "patient_count": count,
            }
        except Exception as e:
            summary["files_failed"] += 1
            summary["per_file"][filename] = {
                "status": "error",
                "error": f"{type(e).__name__}: {e}",
            }
            summary["errors"].append(f"{filename}: {e}")

    return summary


# --- CLI entry point for standalone testing ---
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )

    patients = process_all_data()

    # Print a few samples from each source
    sources = {}
    for p in patients:
        sources.setdefault(p.source_hospital, []).append(p)

    print(f"\n{'=' * 60}")
    print(f"PIPELINE RESULT: {len(patients)} patients from {len(sources)} hospitals")
    print(f"{'=' * 60}")

    for source, plist in sorted(sources.items()):
        print(f"\n--- {source} ({len(plist)} patients) ---")
        sample = plist[0]
        print(f"  First: {sample.patient_id} | {sample.name} | "
              f"{sample.gender} | {sample.blood_group}")
        print(f"  Dx: {sample.diagnosis} | Meds: {sample.medications}")
