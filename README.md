# Dhaga Operations — two-task FDE MVP

A small Python/Streamlit app for:
1. Reading and classifying return reasons from WhatsApp, app and support CSV exports.
2. Standardising catalogue colour, fabric and size labels with human review.

The default mode works without credentials. It uses **offline rules, not AI**, and session-only storage. Switch on live AI and Supabase after setup. Offline mode is a walkthrough; the coursework two-model requirement must be demonstrated in live mode.

## Quick start in VS Code (Python 3.12 recommended)

Extract the ZIP, then open the **dhaga_ops** folder in VS Code (File → Open Folder). Install the recommended Python extension. Open Terminal → New Terminal.

Windows PowerShell:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m streamlit run app.py
```
If PowerShell blocks activation, run `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` and `.\.venv\Scripts\python.exe -m streamlit run app.py` directly instead.

macOS/Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m streamlit run app.py
```

Open the local URL printed in the terminal. Select **Return reasons**, keep **Use included synthetic data** selected, and click **Process records**. Select Catalogue standardisation and do the same. Both should be usable without narration. Setup time depends on download speed; the clean-environment dependency install was verified during delivery, but do not promise five minutes on every connection.

When updating an existing installation, keep your current `.env`; do not overwrite it with `.env.example`. Restart Streamlit after replacing app files or `.streamlit/config.toml`.

In VS Code select the .venv interpreter using Python: Select Interpreter. The included Run and Debug configuration also launches Streamlit.

## WhatsApp conversation panel

1. Open **Return reasons** and process your CSV (offline mode works too).
2. Select a row in **Processed messages**, using its selector on the left, or choose a message from **Conversation** in the right-hand WhatsApp panel.
3. The separate panel shows the customer message and an action-specific confirmation prompt: `fit_too_small` / `fit_too_large` offers a size exchange, `damaged` offers return of the damaged item and a replacement, and other reasons keep the return prompt. Click **YES** or **NO** to record the reply. The panel stays open with the reply and acknowledgement visible.
4. Switch messages to view their individual responses. **CANCEL** clears the active conversation without changing a saved reply.
5. Export the results to retain `return_response`, `response_at`, `response_action` and `requested_action`. `response_action` records which offer was answered; `requested_action` is filled only for YES and is empty for NO. If a correction changes the offered action, the chat asks for a new confirmation instead of treating the earlier answer as acceptance of the new action. Replies are session data only; the existing Supabase schema saves classifications.

The panel is a local demonstration and sends no WhatsApp messages or refunds. Classification approval remains a separate action. Reprocessing or loading saved records replaces session results and clears their replies. No extra API keys or SQL migrations are needed.

## Seller-hub theme and category pie chart

The appearance follows [Group13 Dhaga & Co, development/megha](https://github.com/memurthy123-create/Group13_Dhaga-Co/tree/development/megha) (reference commit `b271411bf13c09eed0419300640ee55c8e941362`): cream background, burgundy accents, serif brand heading, rounded buttons and green/white WhatsApp-style bubbles. `.streamlit/config.toml` includes its theme colours alongside the existing upload-size and telemetry settings. Run Streamlit from this project folder and restart the server after replacing the files so it reads the theme configuration.

After processing Return reasons, a **Category types · Primary reason** pie chart appears below the processed table. Hover for the category, number of messages and percentage. It includes valid classifications awaiting human review, `not_return` and `insufficient_information`; failed records are excluded. These are message counts rather than deduplicated case or order counts. The chart refreshes after a human correction.

Selecting any processed return row shows its conversation in the separate right-hand panel: no ON HOLD status or additional confirmation gate is required. YES/NO records the reply in the session and CSV; CANCEL clears the conversation selection. The existing classification review remains available independently. The reference project's COD eligibility, retry, courier and hold workflows are not part of this returns/catalogue app.

## Supabase setup

1. Create your own Supabase project.
2. Open its SQL editor, paste **sql/schema.sql**, and run it. This creates two workflow tables, a review log, timestamp triggers and an atomic review function.
3. Copy your project URL and server-side service-role key to `.env`:
```dotenv
SUPABASE_URL=https://YOUR-PROJECT.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVER_KEY
APP_PASSWORD=YOUR_STRONG_TEAM_PASSWORD
```
4. Restart the app. Enable **Use Supabase storage**, enter your team password, then process data and click **Save current results to Supabase**.
5. **Load saved records** retrieves up to 500 rows. Human approvals in Supabase mode save immediately using a transaction and write an audit record.

The Streamlit Python server holds the key; it is never sent to browser JavaScript. Tables have RLS enabled and anonymous/authenticated clients have no direct table grants. Do not publish .env or put the service-role key in screenshots. This is a simple shared-password coursework app, not a production multi-user access system. Use only synthetic records when publicly demonstrating it.

Reprocessing/saving the same IDs overwrites the current result. Review history remains in review_log, but this MVP does not provide concurrent-edit conflict resolution. Avoid parallel reviewers. Save each upload deliberately; loads are limited to 500 rows and the app is not a historical data warehouse.

## Live AI setup (two different models)

Add these values to .env, then restart:
```dotenv
OPENAI_API_KEY=YOUR_KEY
TYPESAFE_API_KEY=YOUR_TYPESAFE_KEY
MODEL_A_PROVIDER=typesafe
MODEL_A=jev-latest
MODEL_B=gpt-4o
APP_PASSWORD=YOUR_STRONG_TEAM_PASSWORD
```

These are configurable model identifiers, not claims about the latest or optimal models. Jev uses the TypeSafe API; GPT-4o uses OpenAI. Both accounts require access and billing. With MODEL_A_PROVIDER=typesafe, MODEL_A must be a TypeSafe Jev model ID. DeepSeek and OpenRouter alternatives are described under Provider selection below. MODEL_B must support OpenAI structured output and temperature=0. The app rejects identical identifiers. For paid usage switch **Use live AI** on and enter the password.

- Model A handles return-language classification and uncertain catalogue mappings.
- Model B reviews results flagged for review or below 0.85 model confidence.
- Exact known catalogue aliases use code first; an LLM does not earn a call for lowercasing or arithmetic.
- **Prompt chaining** passes the first decision plus original record to the reviewer.
- **Routing** sends uncertain outputs to Model B and unresolved/disagreeing cases to human review.
- Jev uses predefined Choice questions, validated and mapped to Pydantic schemas. GPT-4o uses structured output and temperature 0. Jev has no temperature parameter. Evidence is the full original return message; catalogue shade and composition retain their raw text. Explanations for Jev are code templates, not model reasoning.
- Every call has a 40-second timeout and at most two attempts. Failure stays visible; no silent rule fallback in live AI classification.
- Jev supplies probability-based confidence; the app uses the minimum across questions. GPT confidence remains self-reported. The 0.85 routing threshold is an initial setting, not a validated threshold for Hinglish. Evaluate on labelled records; do not equate 0.9 confidence with 90% correctness.

The synthetic data contains ambiguity so you can demonstrate both models. Confirm the usage table records both before claiming the two-model requirement is met. Run a small subset first: 161 sequential live records can take several minutes and incur charges. Requests are sequential to keep the code simple and avoid rate spikes.

Sources consulted: OpenAI's Python structured-output examples at https://github.com/openai/openai-python/blob/main/examples/responses/structured_outputs.py and Supabase's Python upsert reference at https://supabase.com/docs/reference/python/upsert . No live API calls or database provisioning were performed while preparing this package.

## Inputs and sample datasets

**Every included record is synthetic.** There are 161 source messages, 60 catalogue SKUs, 150 order headers, 150 order lines, 30 manually specified return labels and 60 catalogue labels. Some messages refer to the same case; one case has conflicting reasons. Other examples cover negation, unknown SKUs, blanks, Hindi/Hinglish, blended fabric, numeric vendor sizes, missing attributes and instructions embedded in messages.

`data/returns.csv` columns: message_id, source (whatsapp/app/support), case_id, order_id, sku, text.
`data/catalogue.csv` columns: sku, vendor_id, product_name, colour_raw, fabric_raw, size_raw, size_chart_id, chest_cm.

These schemas are MVP design choices, not verified Dhaga exports. Existing exports need a mapping to the templates. The files are already populated and also available through the app's download buttons. Each uploaded CSV accepts at most 500 rows and 5 MB. CSV is the only input format in this version; no live WhatsApp/Gupshup, app database, or Freshdesk connector is included.

Select **Use included synthetic data** off to process your own CSV. For return uploads, provide a reference catalogue through the optional reference upload to verify SKU membership. Without it, records stay reviewable because product links are unverified. The app checks SKU membership, not authenticated ownership of a customer's order or case. order_id/case_id are supplied source identifiers; do not infer case identity from similar text. orders.csv and order_items.csv are illustrative fixtures, not an implemented inventory/order integration.

Preserve a shared case_id across channels to deduplicate case-level counts. Conflicting case reasons are excluded from case counts and reported separately. Message counts are distinct from case, order and unit counts. The case-deduplication summary uses ready/approved classifications and excludes tracking enquiries; records needing review and failures remain visible separately. The primary-reason pie chart includes every valid classification, including review-pending results, tracking enquiries (`not_return`) and `insufficient_information`, and excludes failures. No return rates, lost profit, causal fit claims or logistics savings are calculated without denominators and verified costs.

Catalogue output keeps raw values and vendor measurements. Navy becomes family Blue with shade Navy. Cotton/polyester composition becomes Blend with the original composition detail. Numeric sizes remain Vendor Specific. One Size requires review; M is only a label, not a universal measurement. Product facts are never inferred from customer complaints or overwritten in an external system. External publishing should use the human-approved export only.

## Files you need to understand

| File | Purpose |
|---|---|
| app.py | Two task screens, review forms, summaries, save/load and exports |
| dhaga/schemas.py | Input and model-output validation |
| dhaga/rules.py | Transparent offline demo and exact catalogue mappings |
| dhaga/models.py | Two-model calls, prompts, bounded retries and token logging |
| dhaga/workflows.py | Validation, routing, review and safe CSV export |
| dhaga/storage.py | Supabase upsert/load and atomic review persistence |
| dhaga/mock_chat.py | Separate WhatsApp conversation panel, message selection and session replies |
| dhaga/ui.py | Seller-hub appearance and primary-reason pie chart |
| .streamlit/config.toml | Cream/burgundy theme, upload-size limit and telemetry setting |
| sql/schema.sql | Database tables, access restrictions and review audit transaction |
| scripts/generate_mock_data.py | Recreates the synthetic CSVs |
| scripts/evaluate.py | Compares outputs with supplied synthetic labels |
| tests/ | Failure/routing/data-integrity and UI checks |
| docs/ | Discovery template, build note and test report |

There is no graph database, vector database, image model, training pipeline or multi-agent framework. These two bounded workflows do not require them.

## Tests and evaluation

The latest codebase passed **39 automated tests**, covering both task screens, human review, provider failure handling, the primary-reason chart, conversation switching, isolated customer replies, CANCEL and CSV export. Provider/storage interface tests use simulated responses; live provider accounts and a real Supabase save/load cycle still need to be checked with your credentials.

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m scripts.evaluate
```
Optional paid live evaluation after configuring credentials:
```bash
python -m scripts.evaluate --live
```
The labels are separate from model inputs. Demo rules were designed with knowledge of the synthetic examples, so demo accuracy is not an independent generalisation estimate. Obtain a genuinely unseen, human-labelled sample before assessing live quality or deployment readiness. The evaluator reports exact match and review workload; extend to class-specific precision/recall on that sample. Both failures and uncertainty are part of the results.

## Costs and operations

Fill the four `MODEL_*_USD_PER_MILLION` settings with verified current input/output prices. Blank prices show **unknown**, not zero. The app records each request's model, attempt, tokens, latency and status. Failed requests can lack usage even if billed; compare with provider billing. Cost = input tokens × input price / 1,000,000 + output tokens × output price / 1,000,000, summed across both models and retries.

Weekly extrapolation: measured average cost per processed message × actual messages/week, plus review time and hosting. The brief's 44% Other share and 31% returns imply about 6,547 Other records/week only if the return denominator is all 48,000 orders and there is one record per return. WhatsApp/ticket duplicates break that assumption; measure actual deduplicated workload. For catalogue work use actual records processed, not 60 model calls per SKU by default. This app sends one uncertain product record per call.

## Deploy for the final presentation

The brief requires both local reproducibility and a public frontend URL. Localhost alone is not the final submission. A Dockerfile is included for a host accepting Docker (including a Hugging Face Docker Space). Configure API/database variables as host secrets; never include .env in the image. Ensure port 7860 is exposed. You can deploy the offline demo first, then configure authenticated live operation. This package has **not been deployed** and contains no live URL.

## Coursework documents

Complete docs/discovery_note_template.md with your group before its first project code commit. This package already contains code: do not backdate your discovery note; tell your mentor the actual sequence if necessary. The two-page-target build note is a starting draft, not invented experiment evidence. Everyone must explain the whole app. Present a failure on purpose: blank return text, unknown SKU, numeric size or unavailable model. Show the review queue and explain what the operations user does next.

## Jev and streaming notes

Get TYPESAFE_API_KEY from https://console.typesafe.ai and restart after editing .env. Confirm usage logs show provider typesafe / role A and openai / role B. resolved_model logs the Jev version behind its alias. Do not send a TypeSafe key to OpenAI. Jev API contract: https://docs.typesafe.ai/api ; model IDs: https://docs.typesafe.ai/models . Jev does not generate free text, so Python preserves original evidence/details and generates the explanation template. Test Hindi/Hinglish on labelled examples before relying on confidence.

Live streaming is an extension design, not implemented in this CSV MVP. See docs/streaming.md.

## When all live records fail

Do not keep processing the full CSV. Run one synthetic Jev connection check from the project terminal:

```bash
python scripts/check_jev.py
```

This sends one small test (and may make one retry for a transient failure). It reads .env without displaying keys. HTTP 401 means authentication was rejected: verify TYPESAFE_API_KEY is a key from the official TypeSafe console, not the OpenAI key. HTTP 402 indicates billing/credit; 403 access; 404 endpoint/model; 422 request validation. A network diagnostic means connectivity/proxy/firewall/timeout; a response-validation diagnostic means the API replied but the app could not accept its schema. Correct the reported cause and restart Streamlit before running a five-row sample.

The error column and usage log show safe diagnostics and HTTP status where available. When DEBUG_ERRORS=true, provider response bodies and tracebacks also appear in the terminal and diagnostics expander, with known API keys redacted. DEBUG_ERRORS=false disables that detailed output. Persistent configuration failures stop subsequent API calls in the batch; remaining records show Not attempted. The app no longer displays green success when rows fail, or a zero-cost estimate when token counts are missing. Failed calls without usage remain cost unknown; provider billing is authoritative.

## Provider selection and direct error printing

Current build caption: **Build: separate WhatsApp conversation panel 2026-10-04**. It appears below the Operations desk heading. If you see an older build caption, stop Streamlit and restart from the updated project folder.

Changing MODEL_A alone does not change the API provider. Select one of these configurations in .env. Model B remains GPT-4o with OPENAI_API_KEY. Restart after saving.

Jev through TypeSafe:
```dotenv
MODEL_A_PROVIDER=typesafe
MODEL_A=jev-latest
TYPESAFE_API_KEY=YOUR_TYPESAFE_KEY
DEBUG_ERRORS=true
```

DeepSeek through OpenRouter (use a key from OpenRouter; confirm the model ID in its catalogue):
```dotenv
MODEL_A_PROVIDER=openrouter
MODEL_A=deepseek/deepseek-v4.1-flash
OPENROUTER_API_KEY=YOUR_OPENROUTER_KEY
DEBUG_ERRORS=true
```

DeepSeek direct (use a key from the DeepSeek platform):
```dotenv
MODEL_A_PROVIDER=deepseek
MODEL_A=deepseek-flash
DEEPSEEK_API_KEY=YOUR_DEEPSEEK_KEY
DEBUG_ERRORS=true
```

The model IDs above must be available to your provider account. Direct DeepSeek uses native IDs; OpenRouter uses provider/model IDs. TypeSafe accepts Jev IDs. The code rejects a DeepSeek ID aimed at TypeSafe before sending any request.

Run this synthetic single-record check before processing the CSV:
```bash
python scripts/check_model.py
```

It prints the provider, model and error traceback/HTTP response body into the VS Code terminal, with known API keys redacted. DEBUG_ERRORS=true also prints app errors into the Streamlit terminal and exposes a Provider error output and traceback expander within Model usage and cost. Use DEBUG_ERRORS=false after diagnosis. Do not share keys or customer data from debug output.

The DeepSeek/OpenRouter adapter requests JSON object output and then validates it against the existing Pydantic decision schema. Invalid or missing fields fail visibly. Unlike Jev, this adapter can generate evidence and explanations. The existing workflow checks exact source evidence and preserves original product data. Confirm both provider accounts work with a small sample before the assignment demonstration.

Price configuration is specific to your selected provider and model. When replacing Jev with DeepSeek, clear the two MODEL_A price fields until you verify DeepSeek/OpenRouter pricing; keeping Jev's prices would give the wrong estimate.

Official API references: https://api-docs.deepseek.com/ ; https://api-docs.deepseek.com/guides/json_mode ; https://openrouter.ai/docs/api-reference/overview .
