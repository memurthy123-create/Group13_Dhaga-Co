"""One Supabase table per workflow plus an append-only review log."""
import os
from supabase import create_client

class SupabaseStore:
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise ValueError("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env first.")
        self.client = create_client(url, key)

    def save(self, records):
        if not records:
            return
        task = records[0]["task"]
        table = "return_records" if task == "returns" else "catalogue_records"
        payload = [{k: r[k] for k in ["record_id", "raw", "input_hash", "decision", "status", "reviewed_by", "review_note", "previous_decision", "engine", "error", "reviewer_used"]} for r in records]
        for start in range(0, len(payload), 100):
            self.client.table(table).upsert(payload[start:start + 100], on_conflict="record_id").execute()

    def load(self, task):
        table = "return_records" if task == "returns" else "catalogue_records"
        rows = self.client.table(table).select("*").order("record_id").limit(500).execute().data
        return [{**r, "task": task} for r in rows]

    def save_review(self, before, after):
        # One database transaction records the old/new values and the final record.
        payload = {k: after[k] for k in ["record_id", "raw", "input_hash", "decision", "status", "reviewed_by", "review_note", "previous_decision", "engine", "error", "reviewer_used"]}
        self.client.rpc("save_dhaga_review", {"p_task": after["task"], "p_record": payload, "p_before": before.get("decision")}).execute()
