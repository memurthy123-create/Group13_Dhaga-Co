import hashlib
import json
import pandas as pd
from .schemas import ReturnInput, CatalogueInput
from .rules import standardise_rules
from .errors import ModelFailure, capture_error

MAX_ROWS = 500

def read_input(data, task):
    if hasattr(data, "seek"):
        data.seek(0)
    frame = pd.read_csv(data, dtype=str, keep_default_na=False)
    schema = ReturnInput if task == "returns" else CatalogueInput
    required = list(schema.model_fields)
    missing = set(required) - set(frame.columns)
    if missing:
        raise ValueError("Missing columns: " + ", ".join(sorted(missing)))
    if len(frame) > MAX_ROWS:
        raise ValueError(f"At most {MAX_ROWS} rows per MVP upload; split larger files.")
    if frame.empty:
        raise ValueError("File has no records.")
    rows, errors = [], []
    for index, row in frame[required].iterrows():
        record = row.to_dict()
        try:
            rows.append(schema.model_validate(record).model_dump())
        except Exception:
            errors.append(f"Row {index + 2}: invalid fields, source, or length. Check the CSV template.")
    if errors:
        raise ValueError("\n".join(errors[:10]))
    key = "message_id" if task == "returns" else "sku"
    if frame[key].duplicated().any():
        raise ValueError(f"Duplicate {key} values in the upload. Resolve duplicates before processing.")
    return rows

def fingerprint(raw):
    return hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def process(rows, task, gateway, catalogue_skus=None, progress=None):
    results = []
    batch_error = None
    for index, raw in enumerate(rows):
        key = raw["message_id"] if task == "returns" else raw["sku"]
        record = {"record_id": key, "task": task, "raw": raw, "input_hash": fingerprint(raw), "decision": None, "status": "failed", "reviewed_by": None, "review_note": "", "previous_decision": None, "engine": "live_ai" if gateway.live else "offline_rules", "error": "", "reviewer_used": False}
        try:
            if batch_error:
                raise ModelFailure("Not attempted because this batch stopped: " + batch_error)
            if task == "catalogue":
                rules = standardise_rules(raw)
                initial = gateway.decide(task, raw) if rules.needs_review and gateway.live else rules
            else:
                initial = gateway.decide(task, raw)
            final = initial
            if gateway.live and (initial.needs_review or initial.confidence < .85):
                final = gateway.decide(task, raw, previous=initial.model_dump())
                record["reviewer_used"] = True
                record["previous_decision"] = initial.model_dump()
                # Disagreement is reviewed by a person, never silently resolved.
                if task == "returns" and final.primary_reason != initial.primary_reason:
                    final.needs_review = True
                if task == "catalogue" and any(getattr(final, k) != getattr(initial, k) for k in ["colour_family", "fabric", "size_label"]):
                    final.needs_review = True
            if task == "returns":
                if final.evidence and final.evidence not in raw["text"]:
                    final.needs_review = True
                    final.explanation += " Evidence is not an exact original-text span."
                if final.primary_reason in ["other", "insufficient_information"]:
                    final.needs_review = True
                if not raw["case_id"] or not raw["sku"] or (catalogue_skus is not None and raw["sku"] not in catalogue_skus):
                    final.needs_review = True
                    final.explanation += " Case/SKU link is missing or unverified."
            else:
                if final.colour_family == "Unknown" or final.fabric == "Unknown" or final.size_label in ["Vendor Specific", "Unknown", "One Size"]:
                    final.needs_review = True
                # Composition details must remain the supplied raw value.
                final.fabric_detail = raw["fabric_raw"]
            record["decision"] = final.model_dump()
            record["status"] = "needs_review" if final.needs_review else "ready"
        except ModelFailure as exc:
            record["error"] = str(exc)
            if exc.stop_batch:
                batch_error = str(exc)
        except Exception as exc:
            capture_error(exc, "Unexpected workflow error")
            record["error"] = "Processing failed. Retry later or classify manually; no result was silently accepted."
        results.append(record)
        if progress:
            progress((index + 1) / len(rows))
    return results

def review(record, decision, reviewer, note):
    from .schemas import ReturnDecision, CatalogueDecision
    if not reviewer.strip():
        raise ValueError("Enter a reviewer name.")
    schema = ReturnDecision if record["task"] == "returns" else CatalogueDecision
    valid = schema.model_validate(decision).model_dump()
    valid["needs_review"] = False
    return {**record, "decision": valid, "previous_decision": record["decision"], "status": "approved", "reviewed_by": reviewer.strip(), "review_note": note.strip(), "error": ""}

def flat_results(records):
    return pd.DataFrame([{**r["raw"], **(r["decision"] or {}), "status": r["status"], "engine": r["engine"], "reviewer_used": r["reviewer_used"], "review_note": r["review_note"], "error": r["error"],
                          **({"return_response": r.get("mock_return_response", ""), "response_at": r.get("mock_response_at", ""),
                              "response_action": r.get("response_action", ""), "requested_action": r.get("requested_action", "")} if r['task'] == 'returns' else {})} for r in records])

def csv_export(frame):
    # Spreadsheet formula injection protection for exported text.
    def safe(value):
        if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
            return "'" + value
        return value
    return frame.map(safe).to_csv(index=False).encode("utf-8-sig")
