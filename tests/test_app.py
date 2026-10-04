from pathlib import Path
from streamlit.testing.v1 import AppTest

def test_both_screens_and_human_review():
    app=AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py',default_timeout=30).run()
    assert not app.exception
    app.button[0].click().run()
    assert not app.exception
    assert app.metric[0].value=='161'
    app.text_input[0].set_value('Neha')
    app.button[-1].click().run()
    assert not app.exception
    assert app.session_state['results_returns'][0]['status']=='approved'
    app.radio[0].set_value('Catalogue standardisation').run()
    app.button[0].click().run()
    assert not app.exception
    assert app.metric[0].value=='60'
    assert app.session_state['results_catalogue'][0]['raw']['chest_cm']=='86'


def test_provider_debug_output_is_visible():
    app=AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py',default_timeout=30)
    app.session_state['usage']=[{'status':'failed','estimated_usd':None,'usage_known':False,'error_debug':'Traceback example\nProvider response body: rejected'}]
    app.run()
    assert not app.exception
    assert any('Traceback example' in x.value for x in app.code)
    assert any('Cost incomplete' in x.value for x in app.warning)


def test_mock_chat_yes_no_cancel_and_export():
    from dhaga.models import ModelGateway
    from dhaga.workflows import process, read_input, csv_export, flat_results
    from dhaga.mock_chat import chat_html
    root = Path(__file__).resolve().parents[1]
    records = process(read_input(root / 'data/returns.csv', 'returns')[:2], 'returns', ModelGateway(live=False))
    original = records[1]['decision'].copy()
    app = AppTest.from_file(root / 'app.py', default_timeout=30)
    app.session_state['results_returns'] = records
    app.session_state['mock_chat_index'] = 1
    app.run()
    assert not app.exception
    assert any('exchange this item' in x.proto.body for x in app.get('html'))
    assert not any('wa-bubble' in x.value for x in app.markdown)
    next(b for b in app.button if b.key == 'mock_chat_yes').click().run()
    assert not app.exception
    records = app.session_state['results_returns']
    assert records[1]['mock_return_response'] == 'yes'
    assert 'mock_return_response' not in records[0]
    assert records[1]['decision'] == original
    assert any(b.key == 'mock_chat_yes' for b in app.button)
    assert b'return_response' in csv_export(flat_results(records))
    assert b'mock_return_response' not in csv_export(flat_results(records))
    assert all('mock' not in x.value.lower() for x in app.markdown)
    assert all('mock' not in x.value.lower() for x in app.caption)
    assert all('mock' not in x.proto.body.lower() for x in app.get('html'))
    app.session_state['mock_chat_index'] = 1
    app.run()
    next(b for b in app.button if b.key == 'mock_chat_no').click().run()
    assert app.session_state['results_returns'][1]['mock_return_response'] == 'no'
    app.session_state['mock_chat_index'] = 1
    app.run()
    next(b for b in app.button if b.key == 'mock_chat_cancel').click().run()
    assert not app.exception
    assert app.session_state['results_returns'][1]['mock_return_response'] == 'no'
    assert not any(b.key == 'mock_chat_yes' for b in app.button)
    dangerous = {**records[0], 'raw': {**records[0]['raw'], 'text': '<script>alert(1)</script>', 'sku': '<b>sku</b>'}}
    html = chat_html(dangerous)
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert '<b>sku</b>' not in html


def test_message_selection_and_dismiss(monkeypatch):
    from dhaga import mock_chat
    state = {'table': {'selection': {'rows': [1]}}}
    monkeypatch.setattr(mock_chat.st, 'session_state', state)
    mock_chat.select_message('table')
    assert state['mock_chat_index'] == 1
    mock_chat.close_chat()
    assert 'mock_chat_index' not in state
    state['table']['selection']['rows'] = []
    mock_chat.select_message('table')
    assert 'mock_chat_index' not in state


def test_primary_reason_pie_after_processing_and_empty_failure_state():
    from dhaga.ui import primary_reason_counts
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py', default_timeout=30).run()
    assert len(app.get('vega_lite_chart')) == 0
    app.button[0].click().run()
    assert not app.exception
    assert len(app.get('vega_lite_chart')) >= 1
    records = app.session_state['results_returns']
    counts = primary_reason_counts(records)
    assert counts.messages.sum() == len(records)
    assert abs(counts.share.sum() - 1) < 1e-9
    records[0] = {**records[0], 'status': 'failed', 'decision': None}
    app.session_state['results_returns'] = records
    app.run()
    assert not app.exception
    assert primary_reason_counts(records).messages.sum() == len(records) - 1
    assert any('1 failed records excluded' in c.value for c in app.caption)
    app.session_state['results_returns'] = [records[0]]
    app.run()
    assert not app.exception
    assert len(app.get('vega_lite_chart')) == 0
    assert any('No classified messages to chart' in i.value for i in app.info)


def test_primary_reason_counts_include_review_and_non_returns():
    from dhaga.ui import primary_reason_counts
    counts = primary_reason_counts([
        {'status': 'ready', 'decision': {'primary_reason': 'size_fit'}},
        {'status': 'needs_review', 'decision': {'primary_reason': 'size_fit'}},
        {'status': 'approved', 'decision': {'primary_reason': 'not_return'}},
        {'status': 'needs_review', 'decision': {'primary_reason': 'insufficient_information'}},
        {'status': 'failed', 'decision': None},
    ])
    assert counts.set_index('primary_reason').messages.to_dict() == {'size_fit': 2, 'not_return': 1, 'insufficient_information': 1}
    assert counts.share.sum() == 1


def test_separate_conversation_panel_switches_messages_and_keeps_replies():
    from dhaga.models import ModelGateway
    from dhaga.workflows import process, read_input
    root = Path(__file__).resolve().parents[1]
    app = AppTest.from_file(root / 'app.py', default_timeout=30)
    app.session_state['results_returns'] = process(read_input(root / 'data/returns.csv', 'returns')[:2], 'returns', ModelGateway(live=False))
    app.run()
    conversation = next(s for s in app.selectbox if s.label == 'Conversation')
    conversation.set_value(0).run()
    assert not app.exception
    next(b for b in app.button if b.key == 'mock_chat_yes').click().run()
    assert not app.exception
    assert any('YES' in m.proto.body and 'wa-bubble wa-user' in m.proto.body for m in app.get('html'))
    next(s for s in app.selectbox if s.label == 'Conversation').set_value(1).run()
    assert app.session_state['mock_chat_index'] == 1
    assert not app.session_state['results_returns'][1].get('mock_return_response')
    next(b for b in app.button if b.key == 'mock_chat_no').click().run()
    next(s for s in app.selectbox if s.label == 'Conversation').set_value(0).run()
    assert app.session_state['results_returns'][0]['mock_return_response'] == 'yes'
    assert app.session_state['results_returns'][1]['mock_return_response'] == 'no'
    next(b for b in app.button if b.key == 'mock_chat_cancel').click().run()
    assert not app.exception
    assert next(s for s in app.selectbox if s.label == 'Conversation').value is None
    app.radio[0].set_value('Catalogue standardisation').run()
    assert not app.exception
    assert not any(s.label == 'Conversation' for s in app.selectbox)


def test_reason_driven_customer_actions_and_reconfirmation(monkeypatch):
    from dhaga import mock_chat
    from dhaga.models import ModelGateway
    from dhaga.workflows import process, read_input, flat_results
    root = Path(__file__).resolve().parents[1]
    record = process(read_input(root / 'data/returns.csv', 'returns')[:1], 'returns', ModelGateway(live=False))[0]
    state = {'results_returns': [record]}
    monkeypatch.setattr(mock_chat.st, 'session_state', state)
    for reason, action, prompt in [
        ('fit_too_small', 'exchange', 'exchange this item for a different size'),
        ('fit_too_large', 'exchange', 'exchange this item for a different size'),
        ('damaged', 'replace_and_return', 'return it and request a replacement'),
        ('changed_mind', 'return', 'Do you want to return this item'),
    ]:
        record['decision']['primary_reason'] = reason
        original = record['decision'].copy()
        assert mock_chat.return_offer(record)[0] == action
        assert prompt in mock_chat.chat_html(record)
        mock_chat.save_reply(0, 'yes')
        assert record['response_action'] == action and record['requested_action'] == action
        assert record['decision'] == original
        assert 'request has been recorded' in mock_chat.chat_html(record)
        assert flat_results([record]).iloc[0]['requested_action'] == action
        mock_chat.save_reply(0, 'no')
        assert record['requested_action'] == '' and record['response_action'] == action
        assert 'do not want to proceed' in mock_chat.chat_html(record)
    record['decision']['primary_reason'] = 'damaged'
    mock_chat.save_reply(0, 'yes')
    record['decision']['primary_reason'] = 'fit_too_small'
    html = mock_chat.chat_html(record)
    assert 'Please confirm the exchange' in html
    assert 'Your exchange request has been recorded' not in html
    assert record['requested_action'] == 'replace_and_return'
