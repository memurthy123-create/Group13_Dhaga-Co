# Guardrails

All business rules for the COD confirmation workflow are in `guardrails.py`.
`app.py` only draws the screen, talks to Supabase, and carries out what
`guardrails.py` decides. To change a rule, change `guardrails.py`.

## The rules

| # | Guardrail | What it means | Where it is enforced |
|---|---|---|---|
| G1 | No auto-cancellation | CANCEL never cancels the order. The order goes ON_HOLD and a CANCEL_REQUEST ticket is raised. | `decide()` |
| G2 | No response = no shipment | NO_RESPONSE always puts the order ON_HOLD with a NO_CONFIRMATION ticket. | `decide()` |
| G3 | Max retries = 2 | A NO on attempt 1 schedules a retry for the next day. A NO on attempt 2 puts the order ON_HOLD with a NO_CONFIRMATION ticket. | `retry_logic()`, `decide()`, `can_send()` |
| G4 | OTHER goes to support | Free text, or any unrecognised response, is never auto-processed. ON_HOLD plus a CUSTOMER_QUERY ticket. | `decide()` |
| G5 | Cost control | No more than 2 confirmation messages per order. A third send is refused. | `MAX_ATTEMPTS`, `can_send()` |
| G6 | Fail visibly | Every failure (send failure, no response, bad address, max attempts) is shown as a notice in the chat or an error on the page, and stored in the `failure_log` table. The Failures view lists them and can retry failed sends. | `log_failure()` in `app.py` |
| G7 | No external assumptions | No courier or WhatsApp API. Delivery date and slot are computed from the order itself. | `delivery_dates()`, `proposed_slot()` |
| G8 | Human override | Every HOLD creates a support ticket. Only a person resolves it; the app never moves an order out of ON_HOLD. | `decide()` returns a `ticket` for every HOLD |

There is also the eligibility filter: only orders with `payment_mode = COD` and
`order_status = READY_TO_SHIP` are processed (`is_eligible()`, `can_send()`).

## Decision table

This is what `decide(response, attempt_number, address_confirmed)` returns.

| Response | Condition | Action | Order status | Attempt status | Ticket |
|---|---|---|---|---|---|
| YES | address confirmed | CONFIRM | READY_TO_SHIP (confirmed) | COMPLETED | none |
| YES | address wrong / incomplete | HOLD | ON_HOLD | ESCALATED | CUSTOMER_QUERY |
| NO | attempt 1 | RETRY next day | unchanged | COMPLETED | none |
| NO | attempt 2 | HOLD | ON_HOLD | ESCALATED | NO_CONFIRMATION |
| CANCEL | any | HOLD | ON_HOLD | ESCALATED | CANCEL_REQUEST |
| NO_RESPONSE | any | HOLD | ON_HOLD | ESCALATED | NO_CONFIRMATION |
| OTHER / anything else | any | HOLD | ON_HOLD | ESCALATED | CUSTOMER_QUERY |

## Settings you can change

At the top of `guardrails.py`:

| Setting | Value | Meaning |
|---|---|---|
| `MAX_ATTEMPTS` | 2 | Maximum confirmation messages per order |
| `RETRY_AFTER_DAYS` | 1 | Days to wait before the retry after a NO |
| `SLOTS` | 10 AM - 1 PM, 1 PM - 4 PM, 4 PM - 7 PM | Delivery time slots |
| `SLA_MIN_DAYS`, `SLA_MAX_DAYS` | 4, 7 | Delivery date range after `created_at` |

If you raise `MAX_ATTEMPTS`, also change the check on `attempt_number` in
`schema.sql` (`between 1 and 2`), or the database will reject attempt 3.

## Slot rule

The system proposes one slot per order:

- Date: `created_at` + 4 days
- Slot: order number modulo 3 (ORD-10001 -> 10001 % 3 = 2 -> "4 PM - 7 PM")

## Simulated system failure

A failed send (message not sent) is shown in the chat, does not consume an
attempt, and leaves the order status unchanged. This is handled in
`send_confirmation()` in `app.py`, because it is a simulation switch and not a
business rule.
