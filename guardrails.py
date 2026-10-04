"""
Guardrails for the COD confirmation workflow.

Every business rule lives in this file. It is pure Python: no Streamlit, no
database, no network, no ML. app.py asks this module what is allowed and what
must happen next, then carries it out.

See GUARDRAILS.md for the plain-language description of each rule.
"""
from datetime import date, timedelta

# ----------------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------------
MAX_ATTEMPTS = 2                                          # G3, G5
SLOTS = ["10 AM - 1 PM", "1 PM - 4 PM", "4 PM - 7 PM"]    # G7: fixed, not from a courier API
SLA_MIN_DAYS, SLA_MAX_DAYS = 4, 7                         # G7: delivery = created_at + 4..7 days

CHAT_STATUS = "READY_TO_SHIP"          # only these orders get the confirmation chat
CONFIRMED_STATUS = "OUT_FOR_DELIVERY"  # where a confirmed order moves to
HOLD_STATUS = "ON_HOLD"

VALID_RESPONSES = {"YES", "NO", "CANCEL", "OTHER", "NO_RESPONSE"}
NO_REASONS = {"ADDRESS", "TIMESLOT"}   # what the customer can pick after NO

# What the app must do with the order
CONFIRM = "CONFIRM"     # order -> OUT_FOR_DELIVERY
RESLOT = "RESLOT"       # timeslot not suitable: send the next attempt with a later date
HOLD = "HOLD"           # order -> ON_HOLD and a support ticket is created (G8)


# ----------------------------------------------------------------------------
# Eligibility and sending
# ----------------------------------------------------------------------------
def is_eligible(order):
    """FILTER: only COD orders in READY_TO_SHIP are processed."""
    return order["payment_mode"] == "COD" and order["order_status"] == CHAT_STATUS


def can_send(order, attempt_number):
    """G3 / G5: may a confirmation message be sent? Returns (allowed, reason)."""
    if order["payment_mode"] != "COD":
        return False, "PREPAID order: no COD confirmation needed"
    if order["order_status"] != CHAT_STATUS:
        return False, f"order is not in {CHAT_STATUS}"
    if attempt_number > MAX_ATTEMPTS:
        return False, f"max attempts ({MAX_ATTEMPTS}) already used"
    return True, ""


def retry_logic(attempt_number):
    """G3: may the system try again after this attempt? Max 2 attempts in total."""
    return attempt_number < MAX_ATTEMPTS


# ----------------------------------------------------------------------------
# Delivery date and slot (G7: simulated, deterministic)
# ----------------------------------------------------------------------------
def delivery_dates(order):
    """All allowed delivery dates: created_at + 4 to 7 days."""
    created = date.fromisoformat(order["created_at"][:10])
    return [created + timedelta(days=d) for d in range(SLA_MIN_DAYS, SLA_MAX_DAYS + 1)]


def proposed_slot(order, attempt_number=1):
    """The slot the system proposes.
    Attempt 1: earliest date (created_at + 4 days). Each later attempt: one day later.
    Time slot = order number % 3 (same for every attempt)."""
    dates = delivery_dates(order)
    day = dates[min(attempt_number - 1, len(dates) - 1)]
    digits = "".join(ch for ch in order["order_id"] if ch.isdigit()) or "0"
    return f"{day.isoformat()} | {SLOTS[int(digits) % len(SLOTS)]}"


# ----------------------------------------------------------------------------
# Decision engine
# ----------------------------------------------------------------------------
def decide(response, attempt_number, no_reason=None):
    """What must happen for a customer response. Strict rules, no ML.

    no_reason: after a NO the customer says why - "ADDRESS" or "TIMESLOT".

    Returns a dict:
      response           value to store (anything unknown becomes OTHER)
      action             CONFIRM | RESLOT | HOLD
      conf_status        COMPLETED | ESCALATED   (cod_confirmation.status)
      order_status       new orders.order_status, or None if unchanged
      ticket             support ticket issue_type, or None
      address_confirmed  True / False / None
      reason             short code the UI uses to pick its message
    """
    if response not in VALID_RESPONSES:
        response = "OTHER"                                   # G4: never auto-process

    def result(action, conf_status, reason, ticket=None, address_confirmed=None):
        order_status = {CONFIRM: CONFIRMED_STATUS, HOLD: HOLD_STATUS}.get(action)
        return {"response": response, "action": action, "conf_status": conf_status,
                "order_status": order_status, "ticket": ticket,
                "address_confirmed": address_confirmed, "reason": reason}

    if response == "YES":            # customer confirmed date, timeslot and address
        return result(CONFIRM, "COMPLETED", "CONFIRMED", address_confirmed=True)

    if response == "NO":
        if no_reason == "ADDRESS":   # wrong address: a human must fix it
            return result(HOLD, "ESCALATED", "ADDRESS_REJECTED",
                          ticket="CUSTOMER_QUERY", address_confirmed=False)
        if retry_logic(attempt_number):                      # timeslot not suitable
            return result(RESLOT, "COMPLETED", "TIMESLOT_REJECTED")
        return result(HOLD, "ESCALATED", "MAX_ATTEMPTS", ticket="NO_CONFIRMATION")     # G3

    if response == "CANCEL":                                 # G1: no auto-cancellation
        return result(HOLD, "ESCALATED", "CANCEL", ticket="CANCEL_REQUEST")

    if response == "NO_RESPONSE":                            # G2: no response = no shipment
        return result(HOLD, "ESCALATED", "NO_RESPONSE", ticket="NO_CONFIRMATION")

    return result(HOLD, "ESCALATED", "OTHER", ticket="CUSTOMER_QUERY")                 # G4
