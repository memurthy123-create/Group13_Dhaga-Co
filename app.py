from pathlib import Path
import hmac
import os
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from dhaga.models import ModelGateway
from dhaga.errors import capture_error
from dhaga.rules import demo_return, standardise_rules
from dhaga.schemas import REASONS, COLORS, FABRICS, SIZES
from dhaga.storage import SupabaseStore
from dhaga.workflows import read_input, process, review, flat_results, csv_export
from dhaga.mock_chat import select_message, return_chat, close_chat
from dhaga.ui import seller_header, primary_reason_pie

ROOT = Path(__file__).parent
load_dotenv(ROOT / '.env')
st.set_page_config(page_title='Dhaga Operations', page_icon='🧵', layout='wide')
seller_header()
st.title('Operations desk')
st.caption('Read return reasons • Standardise catalogue values • Review exceptions')
st.caption('Build: separate WhatsApp conversation panel 2026-10-04')

with st.sidebar:
    st.header('Run settings')
    live = st.toggle('Use live AI (paid API)', value=False)
    persistent = st.toggle('Use Supabase storage', value=False)
    if live or persistent:
        configured = os.getenv('APP_PASSWORD', '')
        if not configured:
            st.error('Set APP_PASSWORD in .env before enabling live AI or Supabase.')
            st.stop()
        entered = st.text_input('Team app password', type='password')
        if not hmac.compare_digest(entered.encode(), configured.encode()):
            st.info('Enter the team password to continue.')
            st.stop()
    st.info('Offline mode uses simple rules, not AI. Session data disappears when the session ends. Supabase saves only when you click Save.')
    st.caption('No automatic refunds, customer messages, or changes to external catalogue systems.')

mode = st.radio('Choose your task', ['Return reasons', 'Catalogue standardisation'], horizontal=True)
task = 'returns' if mode == 'Return reasons' else 'catalogue'
key = f'results_{task}'
st.session_state.setdefault(key, [])
st.session_state.setdefault('usage', [])
st.session_state.setdefault('audit', [])

if task == 'returns':
    st.write('Import WhatsApp, App, or support exports using the same CSV template. Retain channel and case IDs. An enquiry is not automatically a return.')
    filename = 'returns.csv'
else:
    st.write('Normalise labels while keeping original shades, compositions, vendor sizes and measurements. Proposed results require an explicit human approval before external publishing.')
    filename = 'catalogue.csv'

sample = ROOT / 'data' / filename
st.download_button('Download sample CSV / input template', sample.read_bytes(), file_name=filename)
uploaded = st.file_uploader('Upload CSV (up to 500 records)', type='csv', key=f'upload_{task}')
use_mock = st.checkbox('Use included synthetic data', value=True, key=f'mock_{task}')
reference = None
if task == 'returns' and not use_mock:
    reference = st.file_uploader('Optional reference catalogue CSV (same catalogue template)', type='csv', key='reference_catalogue')
source = sample if use_mock else uploaded
if use_mock:
    st.warning('Synthetic demo data: not Dhaga customer records or evidence of real business savings.')
if source is not None:
    try:
        rows = read_input(source, task)
        st.dataframe(pd.DataFrame(rows).head(15), hide_index=True, width='stretch')
    except Exception as exc:
        st.error(str(exc))
        rows = []
else:
    rows = []

c1, c2 = st.columns(2)
with c1:
    if st.button('Process records', type='primary', disabled=not rows):
        try:
            if live and not os.getenv('OPENAI_API_KEY'):
                raise ValueError('Set OPENAI_API_KEY in .env for live mode.')
            gateway = ModelGateway(live=live)
            progress = st.progress(0.0)
            known = set(pd.read_csv(ROOT / 'data/catalogue.csv', dtype=str)['sku']) if use_mock else None
            # For uploaded returns, catalogue links are unverified unless a matching catalogue is supplied.
            if task == 'returns' and not use_mock:
                known = set(r['sku'] for r in read_input(reference, 'catalogue')) if reference is not None else set()
            st.session_state[key] = process(rows, task, gateway, catalogue_skus=known, progress=progress.progress)
            close_chat()
            st.session_state['results_generation'] = st.session_state.get('results_generation', 0) + 1
            st.session_state['usage'] += gateway.usage()
            st.session_state[f'last_usage_{task}'] = gateway.usage()
            st.session_state[f'last_count_{task}'] = len(rows)
            failed = sum(r['status'] == 'failed' for r in st.session_state[key])
            if failed:
                st.error(f'{failed} records have no decision. Read the error column or Model usage and cost diagnostics. Configuration failures stop further API calls in this batch.')
            else:
                st.success('Processing complete. Inspect the review queue before using results.')
        except Exception as exc:
            st.error(str(exc) if isinstance(exc, ValueError) else 'Processing could not start. Check configuration and try again.')
            details = capture_error(exc, 'Application start or processing error')
            if details:
                st.code(details, language='text')
with c2:
    if persistent and st.button('Load saved records from Supabase'):
        try:
            st.session_state[key] = SupabaseStore().load(task)
            close_chat()
            st.session_state['results_generation'] = st.session_state.get('results_generation', 0) + 1
            st.success('Loaded up to 500 saved records.')
        except Exception:
            st.error('Supabase load failed. Check URL, server key, network and sql/schema.sql setup.')

records = st.session_state[key]
if records:
    frame = flat_results(records)
    a, b, c = st.columns(3)
    a.metric('Input records', len(records))
    b.metric('Needs review', sum(r['status'] == 'needs_review' for r in records))
    c.metric('Failed visibly', sum(r['status'] == 'failed' for r in records))
    if task == 'returns':
        messages, conversation = st.columns([1.7, 1], gap='large')
        with messages:
            st.subheader('Processed messages')
            st.caption('Select a row using the selector on the left to view its WhatsApp conversation.')
            table_key = f"return_messages_{st.session_state.get('results_generation', 0)}"
            st.dataframe(frame, hide_index=True, width='stretch', height=480, key=table_key,
                         on_select=lambda: select_message(table_key), selection_mode='single-row')
        with conversation:
            return_chat()
    else:
        st.dataframe(frame, hide_index=True, width='stretch')
    if task == 'returns':
        primary_reason_pie(records)
    st.download_button('Export all results (includes review status)', csv_export(frame), file_name=f'{task}_results.csv')
    if task == 'returns':
        st.caption('Customer replies are retained in this session and CSV exports. Supabase saving currently stores classifications only.')
    accepted = [r for r in records if r['status'] == 'approved']
    if accepted:
        st.download_button('Export human-approved records only', csv_export(flat_results(accepted)), file_name=f'{task}_approved.csv')
    if persistent and st.button('Save current results to Supabase'):
        try:
            SupabaseStore().save(records)
            st.success('Saved. Re-saving these record IDs updates them; it does not create duplicates.')
        except Exception:
            st.error('Save failed or incomplete. Data remains in this session. Retry is safe for the same record IDs.')

    st.subheader('Human review and correction')
    choices = {f"{r['record_id']} · {r['status']}": i for i, r in enumerate(records)}
    selected = st.selectbox('Select a record (including failures)', list(choices), key=f'selected_{task}')
    idx = choices[selected]
    before = records[idx]
    st.json(before['raw'])
    current = before['decision'] or (demo_return(before['raw']['text']).model_dump() if task == 'returns' else standardise_rules(before['raw']).model_dump())
    with st.form(f'review_{task}_{before["record_id"]}'):
        reviewer = st.text_input('Reviewer name')
        if task == 'returns':
            primary = st.selectbox('Primary reason', REASONS, index=REASONS.index(current['primary_reason']))
            secondary = st.multiselect('Secondary reasons', REASONS[:-2], default=current['secondary_reasons'])
            # 'other' and actual reasons only; schema catches unsupported labels.
            evidence = st.text_area('Evidence from original message', value=current['evidence'])
            new = {**current, 'primary_reason': primary, 'secondary_reasons': secondary, 'evidence': evidence}
        else:
            family = st.selectbox('Colour family', COLORS, index=COLORS.index(current['colour_family']))
            shade = st.text_input('Specific shade', value=current['colour_shade'])
            fabric = st.selectbox('Fabric category', FABRICS, index=FABRICS.index(current['fabric']))
            size = st.selectbox('Size label (no fit equivalence inferred)', SIZES, index=SIZES.index(current['size_label']))
            st.caption('Original fabric detail and vendor measurements are preserved.')
            new = {**current, 'colour_family': family, 'colour_shade': shade, 'fabric': fabric, 'size_label': size}
        note = st.text_area('Review note / reason for correction')
        submitted = st.form_submit_button('Approve this decision')
        if submitted:
            try:
                if task == 'returns' and evidence and evidence not in before['raw']['text']:
                    raise ValueError('Evidence must be copied from the original message.')
                after = review(before, new, reviewer, note)
                if persistent:
                    SupabaseStore().save_review(before, after)
                st.session_state['audit'].append({'record_id': before['record_id'], 'task': task, 'before': before['decision'], 'after': after['decision'], 'reviewer': reviewer, 'note': note})
                st.session_state[key][idx] = after
                st.rerun()
            except Exception as exc:
                st.error(str(exc) if isinstance(exc, ValueError) else 'Review save failed. Your old record was retained; check Supabase setup.')

    if task == 'returns':
        st.subheader('Reason counts and case deduplication')
        accepted_rows = [r for r in records if r['status'] in ['ready', 'approved'] and r['decision']['primary_reason'] != 'not_return']
        view = flat_results(accepted_rows)
        if not view.empty:
            st.bar_chart(view['primary_reason'].value_counts())
            linked = view[view['case_id'] != '']
            conflict_ids = linked.groupby('case_id')['primary_reason'].nunique()
            conflicts = set(conflict_ids[conflict_ids > 1].index)
            consistent = linked[~linked['case_id'].isin(conflicts)].drop_duplicates('case_id')
            st.write(f'Message-level classifications: {len(view)}. Unique linked cases: {linked.case_id.nunique()}. Conflicting cases excluded from case counts: {len(conflicts)}.')
            st.dataframe(consistent.groupby('primary_reason').size().rename('unique_cases').reset_index(), hide_index=True)
            st.caption('Messages and cases are not orders or units. No return rates or savings are inferred without validated denominators and costs.')
    else:
        st.subheader('Catalogue quality summary')
        st.write('Proposed changes are visible above. Use human-approved export for any later external update. This app never edits inventory quantities or assumes cross-vendor size equivalence.')

with st.expander('Model usage and cost'):
    usage = st.session_state['usage']
    if usage:
        u = pd.DataFrame(usage)
        st.dataframe(u.drop(columns=['error_debug'], errors='ignore'), hide_index=True)
        debug_items = [x.get('error_debug') for x in usage if x.get('error_debug')]
        if debug_items:
            with st.expander('Provider error output and traceback'):
                for details in dict.fromkeys(debug_items):
                    st.code(details, language='text')
        if u.estimated_usd.notna().all():
            total = u.estimated_usd.sum()
            st.write(f'Estimated token cost for recorded calls: ${total:.6f} (using your configured prices).')
            recent = st.session_state.get(f'last_usage_{task}', [])
            count = st.session_state.get(f'last_count_{task}', 0)
            if recent and count and all(x['status'] == 'ok' for x in recent):
                workload = st.number_input('Actual weekly input records for selected task (0 = unknown)', min_value=0, value=0, step=100)
                recent_cost = sum(x['estimated_usd'] for x in recent)
                st.write(f'Last batch: ${recent_cost:.6f} / {count} records = ${recent_cost / count:.6f} per record.')
                if workload:
                    st.write(f'Weekly token estimate: ${recent_cost / count:.6f} × {workload} = ${recent_cost / count * workload:.4f}. Excludes hosting and human review.')
        else:
            if any(not x.get('usage_known', x['status'] == 'ok') for x in usage):
                st.warning('Cost incomplete: one or more API calls returned no token counts. This is not proof of zero cost. Read the diagnostic column and check provider billing.')
            else:
                st.info('Cost unknown: fill verified current model prices in .env.')
    else:
        st.write('No live model calls. Offline rules have no API token cost and do not meet the two-model requirement.')
with st.expander('Session review audit'):
    st.json(st.session_state['audit'])
