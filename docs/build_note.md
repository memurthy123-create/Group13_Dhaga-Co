# Build note — draft for the group (two-page target)

## What was built
Two operations screens: return-message classification and catalogue standardisation. CSV imports stand in for WhatsApp/app/support and catalogue exports. Supabase stores raw input, current decisions and reviews. No refunds, customer replies or external inventory writes occur.

## Code versus models
Code validates CSVs and output schemas, preserves raw inputs, maps exact catalogue aliases, routes exceptions, computes counts, exports data and saves reviews. Model A interprets messy text/uncertain attributes. Model B independently reviews difficult first results. Temperature is 0 for both classification/evaluation calls. No creative customer-facing generation is present.

## Patterns and two models
Prompt chaining passes original records and first decisions to Model B. Routing sends uncertainty to Model B and residual uncertainty/disagreement to humans. Removing chaining loses the context needed to review the first decision. Removing routing either reviews everything at higher cost or lets ambiguous cases proceed without a review path. Exact aliases still use code. Configured defaults are jev-latest (TypeSafe) and gpt-4o (OpenAI); group must measure and justify their quality/cost/latency on real-shaped unseen input. Offline demo rules are not two models.

## Cost line
Input/output tokens and elapsed time are logged per request and retry. Enter current model prices before reporting cost. Sum token costs, then multiply observed cost/message by actual chosen workflow volume. Prices and weekly workloads are not fabricated. Ambiguous failure billing, review labour and hosting are additional costs. This build made no paid calls.

## Failure and review
Missing columns/duplicate IDs reject imports. Blank or unknown comments, missing SKU/case links, evidence not present in the source, unknown attributes and vendor-specific sizes enter review. Refusal/invalid/API output gets at most two attempts, then a visible failure. A person can correct a failed row. Supabase review writes and its audit entry are transactional. Reprocessing can overwrite current decisions; shared concurrent editing is out of scope.

## Unexpected issue observed during verification
A negated phrase such as “not tight” is easy for keyword rules to misread as a fit problem. Demo mode conservatively routes negation to review instead of claiming full understanding. This is a real observed limitation, not a measured live-model result. Two-stage review still needs independent evaluation.

## Validation and next steps
See test_report.md for actual checks. Live Supabase/AI/Docker deployment were not exercised without credentials or hosting. Next: initialise Supabase, run a small paid sample, evaluate an unseen labelled set, measure review time, then deploy and rehearse a failure case. Real source adapters, business benefit pilots, per-user access and concurrent review are later work.
