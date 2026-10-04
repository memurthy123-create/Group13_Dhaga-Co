"""
COD Confirmation Desk - reduce RTO with a deterministic confirmation workflow.

Run locally:   streamlit run app.py
Secrets:       .streamlit/secrets.toml  ->  SUPABASE_URL, SUPABASE_KEY

No ML, no real WhatsApp / courier APIs. Everything is rule based and mocked.
"""
import html
from datetime import date, datetime, timedelta, timezone

import streamlit as st
from supabase import create_client

# ----------------------------------------------------------------------------
# Constants (the rules of the system live here)
# ----------------------------------------------------------------------------
# All business rules live in guardrails.py (see GUARDRAILS.md)
from guardrails import (MAX_ATTEMPTS, CONFIRM, RESLOT, CHAT_STATUS, CONFIRMED_STATUS, HOLD_STATUSES,
                        is_eligible, can_send, proposed_slot, decide)

DEMO_BATCH = 20        # demo: how many PLACED orders are moved to READY_TO_SHIP per click

st.set_page_config(page_title="The Dhaga & Co | Seller Hub", page_icon="🧵", layout="wide")


# ----------------------------------------------------------------------------
# Supabase
# ----------------------------------------------------------------------------
@st.cache_resource
def get_db():
    return create_client(st.secrets["SUPABASE_URL"].strip(), st.secrets["SUPABASE_KEY"].strip())


try:
    db = get_db()
except Exception as e:
    # Fail visibly: show the real reason instead of a generic message
    import os
    secrets_path = os.path.join(os.getcwd(), ".streamlit", "secrets.toml")
    st.error("Could not connect to Supabase.")
    st.write("Reason:", f"`{type(e).__name__}: {e}`")
    st.write("Secrets file expected at:", f"`{secrets_path}`")
    st.write("File found there:", os.path.exists(secrets_path))
    if os.path.isdir(os.path.dirname(secrets_path)):
        st.write("Files in .streamlit folder:", os.listdir(os.path.dirname(secrets_path)))
    st.stop()


PAGE_SIZE = 25
LOG_LIMIT = 200


def fetch_orders(status, search, page):
    """One page of orders, filtered in Supabase. Returns (rows, total_count)."""
    q = db.table("orders").select("*", count="exact")
    if status != "All":
        q = q.eq("order_status", status)
    # keep only safe characters so the search text cannot break the filter syntax
    s = "".join(ch for ch in search if ch.isalnum() or ch in " -").strip()
    if s:
        q = q.or_(f"order_id.ilike.%{s}%,customer_name.ilike.%{s}%")
    start = (page - 1) * PAGE_SIZE
    res = q.order("order_id").range(start, start + PAGE_SIZE - 1).execute()
    return res.data, res.count or 0


def fetch_order(order_id):
    rows = db.table("orders").select("*").eq("order_id", order_id).execute().data
    return rows[0] if rows else None


def fetch_confirmations(order_ids):
    """Returns {order_id: [attempt rows sorted by attempt_number]} for the given orders."""
    if not order_ids:
        return {}
    rows = (db.table("cod_confirmation").select("*").in_("order_id", order_ids)
            .order("attempt_number").execute().data)
    grouped = {}
    for r in rows:
        grouped.setdefault(r["order_id"], []).append(r)
    return grouped


def fetch_tickets():
    return (db.table("support_tickets").select("*").order("ticket_id", desc=True)
            .limit(LOG_LIMIT).execute().data)


def fetch_attempt_log():
    return (db.table("cod_confirmation").select("*").order("id", desc=True)
            .limit(LOG_LIMIT).execute().data)


def set_order_status(order_id, status):
    db.table("orders").update({"order_status": status}).eq("order_id", order_id).execute()


# ----------------------------------------------------------------------------
# Chat helpers (chat transcript lives in session only; decisions live in the DB)
# ----------------------------------------------------------------------------
st.session_state.setdefault("chats", {})     # order_id -> [(role, text)]
st.session_state.setdefault("stage", {})     # order_id -> ASK | ADDRESS | SLOT
st.session_state.setdefault("selected", None)


def say(order_id, role, text):
    """role: 'bot' (system message to customer), 'user' (customer), 'notice' (system state)."""
    st.session_state.chats.setdefault(order_id, []).append(
        (role, text, datetime.now().strftime("%H:%M"))
    )


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def slot_label(timeslot):
    """'2026-10-07 | 10 AM - 1 PM' -> 'Wed, 07 Oct 2026, 10 AM - 1 PM'"""
    day, slot = timeslot.split(" | ")
    return f"{date.fromisoformat(day):%a, %d %b %Y}, {slot}"


def confirmation_text(order, timeslot, attempt_number=1):
    if attempt_number == 1:
        intro = (f"Hi {order['customer_name']}! Your Cash-on-Delivery order {order['order_id']} "
                 "is ready to ship.")
    else:
        intro = (f"Hi {order['customer_name']}, here is a new delivery slot for your "
                 f"order {order['order_id']}.")
    return (f"{intro}\n"
            f"Delivery: {slot_label(timeslot)}\n"
            f"Address: {order['address_text']}, Pincode: {order['pincode']}\n"
            "Do confirm your availability. Reply YES, NO or CANCEL, or type your message.")


def log_failure(order_id, failure_type, message, attempt_number=None):
    """G6 fail visibly: every failure is stored in the failure_log table.
    order_id is None for a bulk send failure."""
    try:
        db.table("failure_log").insert(
            {"order_id": order_id, "attempt_number": attempt_number,
             "failure_type": failure_type, "message": message}
        ).execute()
    except Exception as e:
        st.session_state.log_error = (
            f"Failure could not be stored ({type(e).__name__}). "
            "Run failure_log.sql in the Supabase SQL Editor to create the failure_log table.")


def fetch_failures(order_id=None, only_open=False):
    try:
        q = db.table("failure_log").select("*")
        if order_id:
            q = q.eq("order_id", order_id)
        if only_open:
            q = q.eq("resolved", False)
        return q.order("id", desc=True).limit(LOG_LIMIT).execute().data
    except Exception:
        return None        # table missing


def retry_failed_sends():
    """Action on stored failures: resend every unresolved send failure.
    Returns (resent_count, skipped_count)."""
    open_rows = [r for r in (fetch_failures(only_open=True) or [])
                 if r["failure_type"] in ("SEND_FAILURE", "BULK_SEND_FAILURE")]
    resent = skipped = 0
    if any(r["failure_type"] == "BULK_SEND_FAILURE" for r in open_rows):
        resent += send_to_all_pending() or 0
    for oid in sorted({r["order_id"] for r in open_rows if r["order_id"]}):
        order = fetch_order(oid)
        attempts = fetch_confirmations([oid]).get(oid, [])
        pending = attempts and attempts[-1]["status"] == "PENDING"
        if order and not pending and send_confirmation(order, len(attempts) + 1):
            resent += 1
        else:
            skipped += 1      # already sent since, or no longer eligible
    ids = [r["id"] for r in open_rows]
    if ids:
        db.table("failure_log").update({"resolved": True}).in_("id", ids).execute()
    return resent, skipped


def notify_support(order_id, issue_type):
    """Mock support notification = create a ticket for manual (human) handling."""
    db.table("support_tickets").insert(
        {"order_id": order_id, "issue_type": issue_type, "status": "OPEN"}
    ).execute()
    say(order_id, "notice", f"🎫 Support team notified ({issue_type})")


def hold_order(order_id, issue_type, status="ON_HOLD"):
    """Guardrail: anything that is not a clean YES ends here. Never auto-cancel, never ship.
    status is ON_HOLD, or DELIVERY_ON_HOLD when the customer asked to cancel."""
    set_order_status(order_id, status)
    say(order_id, "notice", f"⏸️ Order moved to {status.replace('_', ' ')}")
    notify_support(order_id, issue_type)


def send_confirmation(order, attempt_number, simulate_failure=False):
    """Mock WhatsApp send. Returns True if the message was 'delivered'."""
    oid = order["order_id"]
    allowed, reason = can_send(order, attempt_number)      # guardrails.py
    if not allowed:
        say(oid, "notice", f"⛔ Not sent: {reason}")
        return False

    if simulate_failure:
        # Fail visibly. Attempt is NOT consumed and order status is unchanged.
        msg = (f"SYSTEM FAILURE: confirmation message (attempt {attempt_number}) "
               "was not sent. No attempt consumed. Please send again.")
        say(oid, "notice", "❌ " + msg)
        log_failure(oid, "SEND_FAILURE", msg, attempt_number)
        return False

    timeslot = proposed_slot(order, attempt_number)
    db.table("cod_confirmation").insert(
        {"order_id": oid, "attempt_number": attempt_number, "status": "PENDING",
         "timeslot": timeslot}
    ).execute()
    say(oid, "bot", confirmation_text(order, timeslot, attempt_number))
    st.session_state.stage[oid] = "ASK"
    return True


def fetch_all(table, columns, **filters):
    """Reads every matching row, 1000 at a time (Supabase page limit)."""
    rows, start = [], 0
    while True:
        q = db.table(table).select(columns)
        for col, val in filters.items():
            q = q.eq(col, val)
        chunk = q.order("order_id").range(start, start + 999).execute().data
        rows += chunk
        if len(chunk) < 1000:
            return rows
        start += 1000


def send_to_all_pending(simulate_failure=False):
    """Bulk send attempt 1 to every COD + READY_TO_SHIP order that has no attempt yet.
    Returns the number of messages sent, or None on (simulated) system failure."""
    if simulate_failure:
        return None
    eligible = fetch_all("orders", "order_id,created_at",
                         payment_mode="COD", order_status="READY_TO_SHIP")
    already = {r["order_id"] for r in fetch_all("cod_confirmation", "order_id")}
    new_rows = [{"order_id": o["order_id"], "attempt_number": 1, "status": "PENDING",
                 "timeslot": proposed_slot(o)}
                for o in eligible if o["order_id"] not in already]
    for i in range(0, len(new_rows), 500):
        db.table("cod_confirmation").insert(new_rows[i:i + 500]).execute()
    return len(new_rows)


def demo_move_placed(simulate_failure=False):
    """DEMO: bulk-move the next 20 PLACED COD orders to READY_TO_SHIP.
    Reaching READY_TO_SHIP sends the confirmation message automatically.
    Returns (moved_count, sent_count); sent_count is None on a (simulated) send failure."""
    rows = (db.table("orders").select("*").eq("payment_mode", "COD").eq("order_status", "PLACED")
            .order("order_id").limit(DEMO_BATCH).execute().data)
    if not rows:
        return 0, 0
    ids = [o["order_id"] for o in rows]
    db.table("orders").update({"order_status": CHAT_STATUS}).in_("order_id", ids).execute()
    if simulate_failure:
        return len(ids), None
    db.table("cod_confirmation").insert(
        [{"order_id": o["order_id"], "attempt_number": 1, "status": "PENDING",
          "timeslot": proposed_slot(o)} for o in rows]
    ).execute()
    return len(ids), len(ids)


def process_response(order, conf, response, other_text=None, no_reason=None):
    """Carries out what guardrails.decide() says must happen for this response.
    conf = the PENDING cod_confirmation row for this attempt
    (its timeslot was already proposed and stored when the message was sent)."""
    oid = order["order_id"]
    d = decide(response, conf["attempt_number"], no_reason)           # guardrails.py
    db.table("cod_confirmation").update(
        {"response": d["response"], "response_time": now_iso(),
         "other_reason_text": other_text or d["reason"],
         "address_confirmed": d["address_confirmed"], "status": d["conf_status"]}
    ).eq("id", conf["id"]).execute()
    st.session_state.stage.pop(oid, None)

    if d["action"] == CONFIRM:
        set_order_status(oid, CONFIRMED_STATUS)
        say(oid, "bot", f"Thank you! Your delivery is confirmed for {slot_label(conf['timeslot'])}.")
        say(oid, "notice", f"✅ Order CONFIRMED - moved to {CONFIRMED_STATUS}")

    elif d["action"] == RESLOT:                         # timeslot not suitable: offer a later date
        say(oid, "notice", f"🔁 Timeslot not suitable - proposing a new slot "
                           f"(attempt {conf['attempt_number'] + 1} of {MAX_ATTEMPTS})")
        send_confirmation(order, conf["attempt_number"] + 1)

    else:                                               # HOLD: always visible, always a ticket
        reason = d["reason"]
        if reason == "ADDRESS_REJECTED":
            say(oid, "bot", "Thanks.Please change your address in the App ""myApp/Profile"". Our support team will contact you to correct the address.")
            say(oid, "notice", "⚠️ Address reported incorrect by customer")
            log_failure(oid, "ADDRESS_REJECTED", "Address reported incorrect by customer. "
                        "Order moved to HOLD, support notified.", conf["attempt_number"])
        elif reason == "MAX_ATTEMPTS":
            say(oid, "bot", "Sorry we could not find a suitable slot. "
                            "Our support team will contact you.")
            say(oid, "notice", f"🚫 Max attempts ({MAX_ATTEMPTS}) reached without confirmation")
            log_failure(oid, "MAX_ATTEMPTS", f"Max attempts ({MAX_ATTEMPTS}) reached without confirmation. "
                        "Order moved to HOLD, support notified.", conf["attempt_number"])
        elif reason == "CANCEL":
            say(oid, "bot", "We have received your cancellation request. "
                            "Our support team will contact you.")
        elif reason == "NO_RESPONSE":
            say(oid, "notice", "⌛ No response received from customer")
            log_failure(oid, "NO_RESPONSE", "No response received from customer. "
                        "Order moved to HOLD, support notified.", conf["attempt_number"])
        else:
            say(oid, "bot", "Thanks for your message. Our support team will get back to you.")
        hold_order(oid, d["ticket"], d["order_status"])


# ----------------------------------------------------------------------------
# UI helpers
# ----------------------------------------------------------------------------
BADGE_COLORS = {
    "PLACED": "#6b7280", "READY_TO_SHIP": "#2563eb", "ON_HOLD": "#dc2626",
    "SHIPPED": "#059669", "CANCEL_REQUESTED": "#b45309", "OUT_FOR_DELIVERY": "#0d9488",
    "DELIVERY_ON_HOLD": "#b91c1c",
    "CONFIRMED": "#059669", "AWAITING REPLY": "#d97706", "RETRY DUE": "#7c3aed",
    "ESCALATED": "#dc2626", "COD": "#92400e", "PREPAID": "#0f766e",
}


def badge(label):
    color = BADGE_COLORS.get(label, "#6b7280")
    return (f"<span style='background:{color};color:#fff;padding:2px 9px;border-radius:10px;"
            f"font-size:12px;font-weight:600;white-space:nowrap'>{label}</span>")


def confirmation_state(attempts):
    """Derive a display state from the latest attempt row."""
    if not attempts:
        return None
    last = attempts[-1]
    if last["status"] == "PENDING":
        return "AWAITING REPLY"
    if last["status"] == "ESCALATED":
        return "ESCALATED"
    if last["response"] == "YES":
        return "CONFIRMED"
    return "RETRY DUE"       # NO on the last sent attempt and the next message is not sent yet


st.markdown("""
<style>
/* ---- store look and feel ---- */
.block-container {padding-top:1.2rem; max-width:1400px}
header[data-testid="stHeader"] {background:transparent}
.promo {background:#2b2118;color:#f6ead9;text-align:center;font-size:12.5px;padding:6px;
        letter-spacing:.4px;border-radius:8px 8px 0 0}
.navbar {display:flex;justify-content:space-between;align-items:center;background:#fff;
         padding:14px 22px;border:1px solid #eadfd2;border-top:0;border-radius:0 0 8px 8px;margin-bottom:18px}
.brand {font-family:Georgia,'Times New Roman',serif;font-size:26px;font-weight:700;color:#8c2f39}
.brand span {font-family:sans-serif;font-size:11px;font-weight:600;color:#fff;background:#8c2f39;
             padding:2px 8px;border-radius:10px;margin-left:10px;vertical-align:middle;
             text-transform:uppercase;letter-spacing:.6px}
.navlinks span, .navlinks b {margin-left:22px;font-size:14px;color:#5b4a3c}
.navlinks b {color:#8c2f39;border-bottom:2px solid #8c2f39;padding-bottom:3px}
.tile {background:#fff;border:1px solid #eadfd2;border-radius:10px;padding:14px 18px}
.tile-num {font-size:26px;font-weight:700;color:#2b2118}
.tile-label {font-size:12.5px;color:#7a6858;text-transform:uppercase;letter-spacing:.5px}
h3 {font-family:Georgia,'Times New Roman',serif;color:#2b2118}
.stButton > button, .stFormSubmitButton > button {border-radius:20px;font-weight:600}
/* ---- chat ---- */
.chat-head {background:#075e54;color:#fff;padding:10px 14px;border-radius:10px 10px 0 0;font-weight:600}
.chat-row {display:flex;margin:6px 0}
.bubble {max-width:85%;padding:7px 10px;border-radius:8px;font-size:14px;color:#111;
         white-space:pre-wrap;box-shadow:0 1px 1px rgba(0,0,0,.15)}
.bot  {background:#ffffff;border-top-left-radius:0}
.user {background:#dcf8c6;border-top-right-radius:0;margin-left:auto}
.notice {background:#fff3cd;color:#5c4400;margin:6px auto;font-size:12.5px;text-align:center}
.time {display:block;text-align:right;font-size:10px;color:#667}
</style>
""", unsafe_allow_html=True)


def render_chat(order_id):
    msgs = st.session_state.chats.get(order_id, [])
    with st.container(height=380):
        if not msgs:
            st.caption("No messages yet.")
        for role, text, t in msgs:
            st.markdown(
                f"<div class='chat-row'><div class='bubble {role}'>{html.escape(text)}"
                f"<span class='time'>{t}</span></div></div>",
                unsafe_allow_html=True,
            )


# ----------------------------------------------------------------------------
# Page
# ----------------------------------------------------------------------------
def count_rows(table, **filters):
    q = db.table(table).select("*", count="exact")
    for col, val in filters.items():
        q = q.eq(col, val)
    return q.limit(1).execute().count or 0


# ---- Store-style top bar ----
VIEWS = ["Orders", "COD Confirmation", "Support", "Failures"]
st.session_state.setdefault("view", "Orders")

st.markdown("<div class='promo'>Cash on Delivery orders are confirmed with the customer "
            "before shipping</div>", unsafe_allow_html=True)

# Nav links are real buttons styled as links; the active one is underlined
active = VIEWS.index(st.session_state.view)
st.markdown(f"""<style>
.st-key-navbar {{background:#fff;border:1px solid #eadfd2;border-radius:8px;
                padding:10px 22px;margin-bottom:10px}}
[class*="st-key-nav_"] button {{background:none;border:none;border-radius:0;box-shadow:none;
    color:#5b4a3c;font-weight:500;padding:2px 0;min-height:0;margin-top:8px}}
[class*="st-key-nav_"] button:hover {{color:#8c2f39;background:none;text-decoration:underline}}
.st-key-nav_{active} button {{color:#8c2f39;font-weight:700;border-bottom:2px solid #8c2f39}}
</style>""", unsafe_allow_html=True)

with st.container(key="navbar"):
    nav = st.columns([5.4, 1, 1.9, 1, 1])
    nav[0].markdown("<div class='brand'>The Dhaga &amp; Co<span>Seller Hub</span></div>",
                    unsafe_allow_html=True)
    for i, name in enumerate(VIEWS):
        if nav[i + 1].button(name, key=f"nav_{i}"):
            st.session_state.view = name
            st.rerun()

# ---- Summary tiles ----
tiles = [
    ("Total orders", count_rows("orders")),
    ("Ready to ship", count_rows("orders", order_status="READY_TO_SHIP")),
    ("Out for delivery", count_rows("orders", order_status="OUT_FOR_DELIVERY")),
    ("On hold", count_rows("orders", order_status="ON_HOLD")),
    ("Delivery on hold", count_rows("orders", order_status="DELIVERY_ON_HOLD")),
    ("Open support tickets", count_rows("support_tickets", status="OPEN")),
]
# Clicking a tile loads its list below: an order-status filter, or the tickets list
TILE_FILTERS = {
    "Total orders": "All",
    "Ready to ship": "READY_TO_SHIP",
    "Out for delivery": "OUT_FOR_DELIVERY",
    "On hold": "ON_HOLD",
    "Delivery on hold": "DELIVERY_ON_HOLD",
}
st.session_state.setdefault("show_open_tickets", False)
# Each tile is a real button styled as a card: the number is the button text,
# the caption is added with CSS (::after) using the button's key class.
tile_css = """
[class*="st-key-tile_"] button {background:#fff;border:1px solid #eadfd2;border-radius:10px;
    padding:14px 18px;display:flex;flex-direction:column;align-items:flex-start;
    min-height:86px;cursor:pointer;transition:box-shadow .15s,border-color .15s}
[class*="st-key-tile_"] button:hover {border-color:#8c2f39;box-shadow:0 2px 8px rgba(140,47,57,.18)}
[class*="st-key-tile_"] button p {font-size:26px;font-weight:700;color:#2b2118;margin:0}
[class*="st-key-tile_"] button::after {font-size:12.5px;font-weight:400;color:#7a6858;
    text-transform:uppercase;letter-spacing:.5px}
"""
for i, (label, _) in enumerate(tiles):
    tile_css += f'.st-key-tile_{i} button::after {{content:"{label}"}}\n'
st.markdown(f"<style>{tile_css}</style>", unsafe_allow_html=True)

for i, (col, (label, value)) in enumerate(zip(st.columns(len(tiles)), tiles)):
    if col.button(f"{value:,}", key=f"tile_{i}", width="stretch", help=f"Show: {label}"):
        if label in TILE_FILTERS:
            # set the filter widgets (they are created further down the page)
            st.session_state.f_status = TILE_FILTERS[label]
            st.session_state.f_search = ""
            st.session_state.show_open_tickets = False
        else:
            st.session_state.show_open_tickets = True
        st.session_state.view = "Orders"     # tiles always land on the Orders view
        st.rerun()
st.caption("Confirmation messages go only to COD orders in READY_TO_SHIP. "
           "WhatsApp flow is simulated - no real APIs are called.")

# ---- Other views (reached from the nav links) ----
if st.session_state.view == "COD Confirmation":
    st.subheader("COD confirmation attempts", anchor=False)
    st.caption(f"Every confirmation message sent and the customer's response (latest {LOG_LIMIT}).")
    rows = fetch_attempt_log()
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.caption("No attempts yet.")
    st.stop()

if st.session_state.view == "Support":
    st.subheader("Support tickets", anchor=False)
    st.caption(f"Manual intervention queue (latest {LOG_LIMIT}).")
    rows = fetch_tickets()
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.caption("No tickets yet.")
    st.stop()

if st.session_state.view == "Failures":
    st.subheader("Failure log", anchor=False)
    st.caption("Every failure is stored here: message not sent, no response, wrong address, "
               f"max attempts reached (latest {LOG_LIMIT}).")
    rows = fetch_failures()
    if rows is None:
        st.error("The failure_log table does not exist yet. Run failure_log.sql in the "
                 "Supabase SQL Editor.")
    elif rows:
        open_sends = [r for r in rows if not r["resolved"]
                      and r["failure_type"] in ("SEND_FAILURE", "BULK_SEND_FAILURE")]
        if st.button(f"🔁 Retry failed sends ({len(open_sends)})", type="primary",
                     disabled=not open_sends,
                     help="Resends every unresolved 'message not sent' failure and marks it resolved"):
            resent, skipped = retry_failed_sends()
            st.session_state.retry_msg = (f"Resent {resent} message(s). {skipped} skipped "
                                          "(already sent since, or no longer eligible).")
            st.rerun()
        if "retry_msg" in st.session_state:
            st.success(st.session_state.pop("retry_msg"))
        st.dataframe(rows, width="stretch", hide_index=True,
                     column_order=["id", "created_at", "order_id", "attempt_number",
                                   "failure_type", "message", "resolved"])
    else:
        st.caption("No failures recorded.")
    st.stop()

if "log_error" in st.session_state:
    st.warning(st.session_state.pop("log_error"))

left, right = st.columns([7, 3])

# ------------------------------ LEFT: orders --------------------------------
with left:
    if st.session_state.show_open_tickets:
        st.subheader("Open support tickets", anchor=False)
        open_tickets = (db.table("support_tickets").select("*").eq("status", "OPEN")
                        .order("ticket_id", desc=True).limit(LOG_LIMIT).execute().data)
        if open_tickets:
            st.dataframe(open_tickets, width="stretch", hide_index=True)
            st.caption(f"Showing the latest {LOG_LIMIT} at most.")
        else:
            st.caption("No open tickets.")
        if st.button("Hide tickets"):
            st.session_state.show_open_tickets = False
            st.rerun()

    st.subheader("Orders", anchor=False)
    f = st.columns([1.8, 3, 1])
    # a filter value requested by a button further down is applied before the widget is created
    if "pending_status" in st.session_state:
        st.session_state.f_status = st.session_state.pop("pending_status")
    status = f[0].selectbox("Order status", ["All", "PLACED", "READY_TO_SHIP", "OUT_FOR_DELIVERY",
                                             "ON_HOLD", "DELIVERY_ON_HOLD", "SHIPPED",
                                             "CANCEL_REQUESTED"], key="f_status")
    search = f[1].text_input("Search order ID or customer name", key="f_search")

    # reset to page 1 whenever a filter changes
    filters = (status, search)
    if st.session_state.get("last_filters") != filters:
        st.session_state.last_filters = filters
        st.session_state.page = 1
    page = f[2].number_input("Page", min_value=1, step=1, key="page")

    # ---- Sending controls ----
    a = st.columns([2.6, 2, 2.6])
    auto_fail = a[2].checkbox("Simulate system failure on automatic / bulk send", key="auto_fail")
    if a[0].button(f"🚚 Demo: move {DEMO_BATCH} PLACED orders to READY_TO_SHIP", type="primary",
                   help=f"Bulk-updates the next {DEMO_BATCH} PLACED COD orders to READY_TO_SHIP. "
                        "The confirmation message is sent to each of them automatically."):
        moved, sent = demo_move_placed(simulate_failure=auto_fail)
        if moved == 0:
            st.session_state.bulk_msg = ("error", "No PLACED COD orders left to move.")
        elif sent is None:
            msg = (f"SYSTEM FAILURE: {moved} orders moved to READY_TO_SHIP but the confirmation "
                   "messages were not sent. No attempts consumed. Use 'Send to all pending'.")
            log_failure(None, "BULK_SEND_FAILURE", msg)
            st.session_state.bulk_msg = ("error", msg)
        else:
            st.session_state.bulk_msg = ("success", f"{moved} orders moved to READY_TO_SHIP and "
                                                    f"the confirmation message was sent to all {sent}.")
        st.session_state.pending_status = "READY_TO_SHIP"   # show the result on the next run
        st.rerun()
    if a[1].button("📤 Send to all pending",
                   help="Sends attempt 1 to every COD + READY_TO_SHIP order that has no message yet"):
        sent = send_to_all_pending(simulate_failure=auto_fail)
        if sent is None:
            msg = ("SYSTEM FAILURE: bulk confirmation messages were not sent. "
                   "No attempts consumed. Please send again.")
            log_failure(None, "BULK_SEND_FAILURE", msg)
            st.session_state.bulk_msg = ("error", msg)
        else:
            st.session_state.bulk_msg = ("success", f"Confirmation message sent to {sent} orders.")
        st.rerun()
    if "bulk_msg" in st.session_state:
        kind, msg = st.session_state.pop("bulk_msg")
        (st.error if kind == "error" else st.success)(msg)

    orders, total = fetch_orders(status, search, page)
    pages = max(1, -(-total // PAGE_SIZE))
    st.caption(f"{total} orders · page {page} of {pages}")
    confirmations = fetch_confirmations([o["order_id"] for o in orders])

    widths = [1.3, 1.9, 1.1, 1.9, 1.6, 1.3, 1.5]
    for col, title in zip(st.columns(widths),
                          ["Order ID", "Customer", "Payment", "Order status",
                           "Confirmation", "Attempts", "Action"]):
        col.markdown(f"<b style='white-space:nowrap'>{title}</b>", unsafe_allow_html=True)

    if not orders:
        st.caption("No orders match.")

    for o in orders:
        oid = o["order_id"]
        attempts = confirmations.get(oid, [])
        state = confirmation_state(attempts)
        c = st.columns(widths)
        c[0].write(oid)
        c[1].write(o["customer_name"])
        c[2].markdown(badge(o["payment_mode"]), unsafe_allow_html=True)
        c[3].markdown(badge(o["order_status"]), unsafe_allow_html=True)
        c[4].markdown(badge(state) if state else "-", unsafe_allow_html=True)
        c[5].write(f"{len(attempts)} / {MAX_ATTEMPTS}" if o["payment_mode"] == "COD" else "-")

        # Chat is only for COD orders in READY_TO_SHIP. PLACED and all other rows have no action.
        if is_eligible(o):
            if c[6].button("Open Chat", key=f"open_{oid}"):
                st.session_state.selected = oid
                st.rerun()

    with st.expander(f"Support tickets (manual intervention queue, latest {LOG_LIMIT})"):
        tickets = fetch_tickets()
        if tickets:
            st.dataframe(tickets, width="stretch", hide_index=True)
        else:
            st.caption("No tickets yet.")

    with st.expander(f"Confirmation attempts log (cod_confirmation, latest {LOG_LIMIT})"):
        all_rows = fetch_attempt_log()
        if all_rows:
            st.dataframe(all_rows, width="stretch", hide_index=True)
        else:
            st.caption("No attempts yet.")

# ------------------------------ RIGHT: chat ---------------------------------
with right:
    oid = st.session_state.selected
    order = fetch_order(oid) if oid else None

    if order:
        attempts = fetch_confirmations([oid]).get(oid, [])
        last = attempts[-1] if attempts else None
        state = confirmation_state(attempts)

        st.markdown(f"<div class='chat-head'>💬 {html.escape(str(order['customer_name']))} "
                    f"· {html.escape(oid)}</div>", unsafe_allow_html=True)
        st.markdown(
            badge(order["payment_mode"]) + " " + badge(order["order_status"]) + " "
            + (badge(state) if state else "")
            + f" &nbsp; <b>Attempt {len(attempts)} / {MAX_ATTEMPTS}</b>",
            unsafe_allow_html=True,
        )
        # No transcript in this browser session: rebuild what is stored in the database
        if not st.session_state.chats.get(oid):
            for r in reversed(fetch_failures(order_id=oid) or []):
                say(oid, "notice", f"❌ {r['message']} (stored {r['created_at'][:16].replace('T', ' ')})")
        has_bot = any(role == "bot" for role, _, _ in st.session_state.chats.get(oid, []))
        if state == "AWAITING REPLY" and not has_bot:
            say(oid, "bot", confirmation_text(order, last["timeslot"] or proposed_slot(order),
                                              last["attempt_number"]))
        render_chat(oid)

        # ---- What can happen next? (deterministic) ----
        if state == "CONFIRMED":
            st.success(f"Confirmed and moved to {CONFIRMED_STATUS}. "
                       f"Delivery: {slot_label(last['timeslot'])}")

        elif not is_eligible(order):
            if order["order_status"] in HOLD_STATUSES:
                st.error(f"Order is {order['order_status'].replace('_', ' ')}. "
                         "Waiting for the support team (manual action).")
            elif order["payment_mode"] != "COD":
                st.info("This is a PREPAID order. Confirmation messages are sent only for "
                        "Cash-on-Delivery orders.")
            else:
                st.warning(f"Not eligible: only COD orders in {CHAT_STATUS} are processed.")

        elif state == "AWAITING REPLY":
            stage = st.session_state.stage.get(oid, "ASK")

            if stage == "ASK":
                st.caption("Customer reply (simulated)")
                b = st.columns(3)
                if b[0].button("YES", key="yes", width="stretch"):
                    say(oid, "user", "YES")
                    process_response(order, last, "YES")
                    st.rerun()
                if b[1].button("NO", key="no", width="stretch"):
                    say(oid, "user", "NO")
                    if last["attempt_number"] < MAX_ATTEMPTS:
                        # ask why before deciding anything
                        say(oid, "bot", "Sorry to hear that. Is the address incorrect, "
                                        "or is the timeslot not suitable?")
                        st.session_state.stage[oid] = "REASON"
                    else:
                        process_response(order, last, "NO")      # 2nd refusal -> HOLD
                    st.rerun()
                if b[2].button("CANCEL", key="cancel", width="stretch"):
                    say(oid, "user", "CANCEL")
                    process_response(order, last, "CANCEL")
                    st.rerun()

                with st.form("other_form", clear_on_submit=True):
                    text = st.text_input("Type a message (treated as OTHER)")
                    if st.form_submit_button("Send") and text.strip():
                        say(oid, "user", text.strip())
                        process_response(order, last, "OTHER", other_text=text.strip())
                        st.rerun()

                if st.button("⌛ Simulate no response", key="noresp", width="stretch"):
                    process_response(order, last, "NO_RESPONSE")
                    st.rerun()

            elif stage == "REASON":
                st.caption("Customer reply (simulated): why NO?")
                b = st.columns(2)
                if b[0].button("Address incorrect", key="why_addr", width="stretch"):
                    say(oid, "user", "Address is incorrect")
                    process_response(order, last, "NO", no_reason="ADDRESS")
                    st.rerun()
                if b[1].button("Timeslot not suitable", key="why_slot", width="stretch"):
                    say(oid, "user", "Timeslot is not suitable")
                    process_response(order, last, "NO", no_reason="TIMESLOT")
                    st.rerun()

        else:
            # Message not sent yet (for example after a send failure): send it from here
            next_attempt = len(attempts) + 1
            fail = st.checkbox("Simulate system failure (message not sent)", key="sim_fail")
            if st.button(f"📤 Send confirmation (attempt {next_attempt} of {MAX_ATTEMPTS})",
                         type="primary", width="stretch"):
                send_confirmation(order, next_attempt, simulate_failure=fail)
                st.rerun()
