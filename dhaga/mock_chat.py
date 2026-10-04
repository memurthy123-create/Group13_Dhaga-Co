"""Local WhatsApp-style conversation panel; no messaging or returns API calls."""
from html import escape
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import streamlit as st


def close_chat():
    st.session_state.pop('mock_chat_index', None)
    st.session_state['return_chat_selection'] = None


def select_message(table_key):
    rows = st.session_state[table_key]['selection']['rows']
    if rows:
        st.session_state['mock_chat_index'] = rows[0]
        st.session_state['return_chat_selection'] = rows[0]
    else:
        close_chat()


def select_conversation():
    index = st.session_state.get('return_chat_selection')
    if index is None:
        st.session_state.pop('mock_chat_index', None)
    else:
        st.session_state['mock_chat_index'] = index


def return_offer(record):
    reason = (record.get('decision') or {}).get('primary_reason')
    if reason in ('fit_too_small', 'fit_too_large'):
        return ('exchange', 'exchange',
                'Hi! Would you like to exchange this item for a different size?',
                'Kya aap is item ko doosre size mein exchange karna chahte hain?')
    if reason == 'damaged':
        return ('replace_and_return', 'return and replacement',
                'Sorry your item arrived damaged. Would you like to return it and request a replacement?',
                'Kya aap damaged item return karke replacement lena chahte hain?')
    return ('return', 'return', 'Hi! Do you want to return this item?',
            'Kya aap is item ko return karna chahte hain?')


def save_reply(index, answer):
    record = st.session_state['results_returns'][index]
    record['mock_return_response'] = answer
    record['mock_response_at'] = datetime.now(timezone.utc).isoformat()
    # Store the offered action separately from the classification and approval.
    record['response_action'] = return_offer(record)[0]
    record['requested_action'] = record['response_action'] if answer == 'yes' else ''


def chat_html(record):
    raw = record['raw']
    text = escape(raw.get('text', '')).replace('\n', '<br>')
    order = escape(raw.get('order_id') or record['record_id'])
    sku = escape(raw.get('sku') or 'Item not linked')
    source = escape(raw.get('source', '').title())
    reply = record.get('mock_return_response', '')
    action, label, english, hinglish = return_offer(record)
    reply_time = ''
    if record.get('mock_response_at'):
        reply_time = datetime.fromisoformat(record['mock_response_at']).astimezone(ZoneInfo('Asia/Kolkata')).strftime('%H:%M')
    response = ''
    if reply in ('yes', 'no') and record.get('response_action', 'return') == action:
        acknowledgement = (f'Thank you. Your {label} request has been recorded.'
                           if reply == 'yes' else f'Thank you for letting us know. You do not want to proceed with the {label}.')
        response = (f'<div class="wa-row"><div class="wa-bubble wa-user">{reply.upper()}'
                    f'<span class="wa-time">{reply_time} ✓✓</span></div></div>'
                    f'<div class="wa-row"><div class="wa-bubble wa-bot">{acknowledgement}'
                    f'<span class="wa-time">{reply_time}</span></div></div>')
    elif reply in ('yes', 'no'):
        response = f'<div class="wa-row"><div class="wa-bubble wa-bot">The requested action has changed. Please confirm the {label} above.</div></div>'
    return f'''<style>
    .wa-window {{border-radius:10px;overflow:hidden;border:1px solid #d7dfdc;
        font-family:Arial,sans-serif;box-shadow:0 2px 10px #0000000a;}}
    .wa-head {{display:flex;align-items:center;gap:12px;background:#075e54;
        color:#fff;padding:14px 16px;}}
    .wa-avatar {{display:grid;place-items:center;width:38px;height:38px;border-radius:50%;
        background:#e6f3ec;color:#075e54;font-size:19px;font-weight:700;flex-shrink:0;}}
    .wa-name {{font-weight:600;font-size:16px;}}
    .wa-meta {{font-size:11px;color:#d0e5de;margin-top:4px;overflow-wrap:anywhere;}}
    .wa-body {{background-color:#efeae2;
        background-image:radial-gradient(#ded7cc 0.7px,transparent 0.7px);
        background-size:12px 12px;padding:14px;min-height:360px;max-height:440px;overflow-y:auto;}}
    .wa-day {{text-align:center;margin:0 auto 16px;font-size:11px;color:#5a6d65;}}
    .wa-day span {{background:#fff8;padding:4px 12px;border-radius:6px;}}
    .wa-row {{display:flex;margin:9px 0;}}
    .wa-bubble {{max-width:85%;padding:8px 11px;border-radius:8px;font-size:14px;
        color:#111;line-height:1.5;overflow-wrap:anywhere;box-shadow:0 1px 1px rgba(0,0,0,.15);}}
    .wa-bot {{background:#fff;border-top-left-radius:0;}}
    .wa-user {{background:#dcf8c6;border-top-right-radius:0;margin-left:auto;}}
    .wa-time {{display:block;text-align:right;font-size:10px;color:#667;margin-top:3px;}}
    </style><div class="wa-window">
    <div class="wa-head"><div class="wa-avatar">D</div><div>
    <div class="wa-name">Dhaga Returns</div><div class="wa-meta">{order} · {sku}</div></div></div>
    <div class="wa-body"><div class="wa-day"><span>Return conversation</span></div>
    <div class="wa-row"><div class="wa-bubble wa-user">{text}<span class="wa-time">{source} · Customer</span></div></div>
    <div class="wa-row"><div class="wa-bubble wa-bot">{english}<br>
    {hinglish}<span class="wa-time">Dhaga Returns</span></div></div>
    {response}</div></div>'''


def return_chat():
    records = st.session_state['results_returns']
    st.subheader('WhatsApp')
    st.selectbox('Conversation', options=range(len(records)), index=None,
                 format_func=lambda i: f"{records[i]['record_id']} · {records[i]['raw'].get('order_id') or 'No order'}",
                 placeholder='Select a message', key='return_chat_selection', on_change=select_conversation)
    index = st.session_state.get('mock_chat_index')
    if index is None or not 0 <= index < len(records):
        st.info('Select a message row or choose a conversation to view the chat here.')
        return
    record = records[index]
    # Render HTML directly: Markdown treats indented divs as literal code blocks.
    st.html(chat_html(record))
    st.caption('Customer reply')
    yes, no, cancel = st.columns(3)
    yes.button('YES', type='primary', width='stretch', key='mock_chat_yes', on_click=save_reply, args=(index, 'yes'))
    no.button('NO', width='stretch', key='mock_chat_no', on_click=save_reply, args=(index, 'no'))
    cancel.button('CANCEL', width='stretch', key='mock_chat_cancel', on_click=close_chat)
