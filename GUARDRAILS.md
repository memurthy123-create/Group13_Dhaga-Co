# Guardrails

All business rules for the COD confirmation workflow are in `guardrails.py`.
`app.py` only draws the screen, talks to Supabase, and carries out what
`guardrails.py` decides. To change a rule, change `guardrails.py`.

## Order flow

```
PLACED  --(bulk status update)-->  READY_TO_SHIP  --(customer says YES)-->  OUT_FOR_DELIVERY
                                         |
                                         +--(anything else that cannot be resolved)-->  ON_HOLD + support ticket
```

- PLACED orders are not touched: no chat, no message.
- When a COD order becomes READY_TO_SHIP, the confirmation message (date, timeslot,
  address) is sent automatically.
- Only COD orders in READY_TO_SHIP have a chat.

## The rules

| # | Guardrail | What it means | Where it is enforced |
|---|---|---|---|
| G1 | No auto-cancellation | CANCEL never cancels the order. The order goes to DELIVERY_ON_HOLD and a CANCEL_REQUEST ticket is raised. | `decide()` |
| G2 | No response = no shipment | NO_RESPONSE always puts the order ON_HOLD with a NO_CONFIRMATION ticket. | `decide()` |
| G3 | Max retries = 2 | A NO for the timeslot on attempt 1 sends attempt 2 with a later date. A NO on attempt 2 puts the order ON_HOLD with a NO_CONFIRMATION ticket. | `retry_logic()`, `decide()`, `can_send()` |
| G4 | OTHER goes to support | Free text, or any unrecognised response, is never auto-processed. ON_HOLD plus a CUSTOMER_QUERY ticket. | `decide()` |
| G5 | Cost control | No more than 2 confirmation messages per order. A third send is refused. | `MAX_ATTEMPTS`, `can_send()` |
| G6 | Fail visibly | Every failure (send failure, no response, wrong address, max attempts) is shown as a notice in the chat or an error on the page, and stored in the `failure_log` table. The Failures view lists them and can retry failed sends. | `log_failure()` in `app.py` |
| G7 | No external assumptions | No courier or WhatsApp API. Delivery date and slot are computed from the order itself. | `delivery_dates()`, `proposed_slot()` |
| G8 | Human override | Every HOLD creates a support ticket. Only a person resolves it; the app never moves an order out of ON_HOLD. | `decide()` returns a `ticket` for every HOLD |

Eligibility filter: only orders with `payment_mode = COD` and
`order_status = READY_TO_SHIP` are processed (`is_eligible()`, `can_send()`).

## Decision table

This is what `decide(response, attempt_number, no_reason)` returns.
After a NO on attempt 1 the chat asks: "Is the address incorrect, or is the
timeslot not suitable?" The answer is `no_reason`.

| Response | Condition | Action | Order status | Attempt status | Ticket |
|---|---|---|---|---|---|
| YES | any attempt | CONFIRM | OUT_FOR_DELIVERY | COMPLETED | none |
| NO | reason: address incorrect | HOLD | ON_HOLD | ESCALATED | CUSTOMER_QUERY |
| NO | reason: timeslot not suitable, attempt 1 | RESLOT: attempt 2 sent with a later date | unchanged | COMPLETED | none |
| NO | attempt 2 (second refusal) | HOLD | ON_HOLD | ESCALATED | NO_CONFIRMATION |
| CANCEL | any | HOLD | DELIVERY_ON_HOLD | ESCALATED | CANCEL_REQUEST |
| NO_RESPONSE | any | HOLD | ON_HOLD | ESCALATED | NO_CONFIRMATION |
| OTHER / anything else | any | HOLD | ON_HOLD | ESCALATED | CUSTOMER_QUERY |

## Settings you can change

At the top of `guardrails.py`:

| Setting | Value | Meaning |
|---|---|---|
| `MAX_ATTEMPTS` | 2 | Maximum confirmation messages per order |
| `SLOTS` | 10 AM - 1 PM, 1 PM - 4 PM, 4 PM - 7 PM | Delivery time slots |
| `SLA_MIN_DAYS`, `SLA_MAX_DAYS` | 4, 7 | Delivery date range after `created_at` |
| `CHAT_STATUS` | READY_TO_SHIP | The status that gets the confirmation chat |
| `CONFIRMED_STATUS` | OUT_FOR_DELIVERY | Where a confirmed order moves to |
| `CANCEL_HOLD_STATUS` | DELIVERY_ON_HOLD | Where an order moves to when the customer asks to cancel |

If you raise `MAX_ATTEMPTS`, also change the check on `attempt_number` in
`schema.sql` (`between 1 and 2`), or the database will reject attempt 3.

## Slot rule

The system proposes one slot per attempt:

- Attempt 1 date: `created_at` + 4 days
- Attempt 2 date: `created_at` + 5 days (one day later)
- Time slot: order number modulo 3, the same for both attempts
  (ORD-10001 -> 10001 % 3 = 2 -> "4 PM - 7 PM")

## Simulated system failure

A failed send (message not sent) is shown on screen, stored in `failure_log`,
does not consume an attempt, and leaves the order status unchanged. This is
handled in `app.py`, because it is a simulation switch and not a business rule.
