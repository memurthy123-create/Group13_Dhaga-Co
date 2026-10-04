"""Seller-hub appearance and primary-reason summary."""
import pandas as pd
import streamlit as st


def seller_header():
    st.markdown('''<style>
    .block-container {padding-top:1.2rem; max-width:1400px}
    header[data-testid="stHeader"] {background:transparent}
    .promo {background:#2b2118;color:#f6ead9;text-align:center;font-size:12.5px;
        padding:6px;letter-spacing:.4px;border-radius:8px 8px 0 0}
    .navbar {background:#fff;padding:14px 22px;border:1px solid #eadfd2;
        border-top:0;border-radius:0 0 8px 8px;margin-bottom:18px}
    .brand {font-family:Georgia,'Times New Roman',serif;font-size:26px;
        font-weight:700;color:#8c2f39}
    .brand span {font-family:sans-serif;font-size:11px;font-weight:600;
        color:#fff;background:#8c2f39;padding:2px 8px;border-radius:10px;
        margin-left:10px;vertical-align:middle;text-transform:uppercase;letter-spacing:.6px}
    h3 {font-family:Georgia,'Times New Roman',serif;color:#2b2118}
    .stButton > button, .stFormSubmitButton > button {border-radius:20px;font-weight:600}
    [data-testid="stMetric"] {background:#fff;border:1px solid #eadfd2;
        border-radius:10px;padding:14px 18px}
    </style><div class="promo">Return insights and catalogue quality · Operations desk</div>
    <div class="navbar"><div class="brand">The Dhaga &amp; Co<span>Seller Hub</span></div></div>''',
                unsafe_allow_html=True)


def primary_reason_counts(records):
    reasons = [r['decision']['primary_reason'] for r in records
               if r.get('status') != 'failed' and r.get('decision')
               and r['decision'].get('primary_reason')]
    counts = pd.Series(reasons, dtype='str').value_counts().rename_axis('primary_reason').reset_index(name='messages')
    counts['category'] = counts['primary_reason'].str.replace('_', ' ').str.title()
    counts['share'] = counts['messages'] / len(reasons) if reasons else 0.0
    return counts


def primary_reason_pie(records):
    st.subheader('Category types · Primary reason')
    counts = primary_reason_counts(records)
    failed = sum(r.get('status') == 'failed' for r in records)
    if counts.empty:
        st.info('No classified messages to chart yet. Resolve the processing errors or classify a record manually.')
        return
    st.vega_lite_chart(counts, {
        'mark': {'type': 'arc', 'stroke': '#faf6f0', 'strokeWidth': 2},
        'encoding': {
            'theta': {'field': 'messages', 'type': 'quantitative', 'stack': True},
            'color': {'field': 'category', 'type': 'nominal',
                      'scale': {'range': ['#8c2f39', '#c87961', '#dba65f', '#74866b', '#547980', '#a88ba3', '#82725f', '#b8aa90', '#526a56', '#6e6193']},
                      'legend': {'title': 'Primary reason', 'orient': 'right'}},
            'tooltip': [{'field': 'category', 'type': 'nominal', 'title': 'Primary reason'},
                        {'field': 'messages', 'type': 'quantitative', 'title': 'Messages'},
                        {'field': 'share', 'type': 'quantitative', 'title': 'Share', 'format': '.1%'}]
        },
        'height': 320,
        'config': {'background': '#faf6f0', 'view': {'stroke': None},
                   'legend': {'labelColor': '#2b2118', 'titleColor': '#2b2118'}}
    }, width='stretch')
    st.caption(f"{int(counts['messages'].sum())} classified messages; {failed} failed records excluded. Includes review-pending classifications, Not Return and Insufficient Information. Counts are messages, not unique cases or orders.")
