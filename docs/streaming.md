# Ingesting live events

This describes the next extension. The delivered app still accepts CSVs; it does not receive webhooks or run a worker.

## Flow

WhatsApp / app / support system -> authenticated HTTPS receiver -> Supabase durable event and queue -> Python background worker -> Jev -> GPT-4o if uncertain -> result tables -> human review screen.

1. WhatsApp: configure the WhatsApp Business Platform provider to send inbound message webhooks to your public HTTPS receiver. Verify the provider's challenge and request signature. Ordinary personal WhatsApp chats are not automatically connected.
2. App: the app backend sends a return-submitted event with an authenticated server request.
3. Support: configure the chosen support platform's ticket-created and ticket-updated webhooks. Where webhooks are unavailable, poll its API using a stored cursor and deduplicate results.
4. The receiver validates the payload and maps it to ReturnInput: message_id, source, case_id, order_id, sku and text. Use an immutable event ID scoped by provider/account; different updates need different event versions. Missing case/SKU links stay unverified; do not guess them.
5. Add an ingestion_events table with event_id, provider, account_id, source_event_id, version, received_at, occurred_at, payload, status, attempts and last_error. Enforce a unique constraint on the provider/account/event/version combination. Add an RPC to insert the event and enqueue its ID atomically. A duplicate must not enqueue a second job. Existing sql/schema.sql does not create these ingestion components.
6. Use Supabase Queues for durable work. Acknowledge receipt to the provider only after the event and queue message are committed. Avoid waiting for AI in the webhook request; let the provider retry when persistence fails.
7. A separate Python worker leases a message with a visibility timeout, loads the event and calls the existing process([raw], 'returns', gateway, catalogue_skus). Use verified product IDs from a catalogue lookup, not guessed text matches. Save the result and mark the event complete before deleting/archiving its queue message. Renew the lease for long AI calls; a crashed worker's message becomes available again.
8. Delivery can repeat. Make result writes idempotent using the ingestion event ID and version. A worker crash after AI but before database commit may still cause a repeated paid AI call. Persist completed results and skip already-completed events. Do not claim exactly-once processing across remote APIs.
9. Retry transient errors with bounded exponential backoff. After a small configured limit, move the item to a failed queue for manual correction/replay. Keep older late-arriving events from replacing a newer or human-approved decision; check event version and review status before writing.
10. Return analysis runs per message; grouping messages by case is a separate aggregation step. A second complaint must not erase the first. Catalogue ingestion can use product-created/product-updated events mapped to CatalogueInput, or scheduled vendor CSV imports where no product API exists.

## Dashboard and deployment

Supabase Realtime can notify an authorised frontend of saved changes. It is not the external source connector or a durable processing queue. The current Streamlit screen requires Load saved records; for a simple extension add timed server refresh. Realtime subscriptions require appropriate authentication and RLS policies; never expose the server secret key to the browser.

Run the receiver and worker as deployed services. VS Code runs them locally for development; source systems require a reachable public HTTPS endpoint. Keep ingestion authentication distinct from APP_PASSWORD. An OpenAI streamed response concerns partial model output, not customer-data ingestion; the existing structured-output request need not stream tokens.

## Minimal end-to-end test

Send one signed/authenticated event, confirm one queue item, process it, then confirm a saved result. Replay the same event and confirm no duplicate job/result. Stop the worker and confirm the queue retains events. Restart and confirm recovery. Simulate AI failure, inspect retry/dead-letter behavior, and replay an older update after a human approval to confirm it does not overwrite the decision.

References: https://supabase.com/docs/guides/queues ; https://supabase.com/docs/guides/realtime ; https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks . Verify the chosen source platform's current event and signature contract when implementing its adapter.
