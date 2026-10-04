import copy
import httpx
import pytest
from dhaga.jev import build_questions, decode_decision
from dhaga.models import ModelGateway
from dhaga.workflows import process

RAW = dict(message_id='M1', source='app', case_id='C1', order_id='O1', sku='S1', text='Kapda phata hua hai, return chahiye')

def response(task='returns', low=False):
    questions = build_questions(task)
    selected = {'primary': 'damaged', 'review': 'no', 'has_damaged': 'yes',
                'colour': 'Blue', 'fabric': 'Blend', 'size': 'M'}
    answers = {}
    for key, q in questions.items():
        value = selected.get(key, 'no')
        answers[key] = dict(type='choice', choice=value, confidence=.6 if low else .95,
                            probabilities={v: float(v == value) for v in q['criteria']})
    return dict(model='jev-1.13.0', answers=answers, usage=dict(input_tokens=120, output_tokens=20))

def test_jev_then_openai_routing_and_cost_logs(monkeypatch):
    monkeypatch.setenv('TYPESAFE_API_KEY', 'fake-typesafe')
    monkeypatch.setenv('OPENAI_API_KEY', 'fake-openai')
    monkeypatch.setenv('MODEL_A', 'jev-latest')
    monkeypatch.setenv('MODEL_A_INPUT_USD_PER_MILLION', '.042')
    monkeypatch.setenv('MODEL_A_OUTPUT_USD_PER_MILLION', '0')
    monkeypatch.setattr('dhaga.models.OpenAI', lambda **kwargs: None)
    g = ModelGateway(live=True)
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs)
        assert kwargs['headers']['Authorization'] == 'Bearer fake-typesafe'
        assert kwargs['json']['state'] == RAW
        assert 'temperature' not in kwargs['json']
        return httpx.Response(200, json=response(low=True), request=httpx.Request('POST', url))
    monkeypatch.setattr('dhaga.models.httpx.post', post)
    class Completions:
        def parse(self, **kwargs):
            from types import SimpleNamespace
            from dhaga.schemas import ReturnDecision
            assert kwargs['model'] == 'gpt-4o'
            assert 'prior_decision' in kwargs['messages'][1]['content']
            result = ReturnDecision(primary_reason='damaged', secondary_reasons=[], evidence=RAW['text'],
                confidence=.95, needs_review=False, explanation='Explicit damage')
            return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=80, completion_tokens=30),
                choices=[SimpleNamespace(message=SimpleNamespace(parsed=result))])
    from types import SimpleNamespace
    g.client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    r = process([RAW], 'returns', g, {'S1'})[0]
    assert r['reviewer_used'] and r['status'] == 'ready'
    assert len(calls) == 1
    assert [c['provider'] for c in g.calls] == ['typesafe', 'openai']
    assert g.calls[0]['resolved_model'] == 'jev-1.13.0'
    assert g.usage()[0]['estimated_usd'] == pytest.approx(120 * .042 / 1000000)

@pytest.mark.parametrize('bad', ['choice', 'missing', 'confidence', 'probabilities'])
def test_malformed_jev_output_rejected(bad):
    body = response()
    if bad == 'choice': body['answers']['primary']['choice'] = 'invented'
    if bad == 'missing': del body['answers']['review']
    if bad == 'confidence': body['answers']['primary']['confidence'] = float('nan')
    if bad == 'probabilities': body['answers']['primary']['probabilities']['damaged'] = -.1
    with pytest.raises((ValueError, KeyError)):
        decode_decision('returns', RAW, build_questions('returns'), body['answers'])

def test_catalogue_preserves_raw_and_numeric_sizes():
    raw = dict(colour_raw='neela navy', fabric_raw='60% cotton 40% polyester', size_raw='38')
    result = decode_decision('catalogue', raw, build_questions('catalogue'), response('catalogue')['answers'])
    assert result.fabric_detail == raw['fabric_raw'] and result.colour_shade == raw['colour_raw']
    assert result.size_label == 'Vendor Specific' and result.needs_review

def test_jev_401_stops_without_retry(monkeypatch):
    g = ModelGateway()
    g.live = True
    monkeypatch.setenv('TYPESAFE_API_KEY', 'fake')
    def post(url, **kwargs):
        return httpx.Response(401, request=httpx.Request('POST', url))
    monkeypatch.setattr('dhaga.models.httpx.post', post)
    r = process([RAW], 'returns', g, {'S1'})[0]
    assert r['status'] == 'failed' and len(g.calls) == 1

def test_jev_rate_limit_retry(monkeypatch):
    g = ModelGateway()
    monkeypatch.setenv('TYPESAFE_API_KEY', 'fake')
    count = []
    def post(url, **kwargs):
        count.append(1)
        return httpx.Response(429 if len(count) == 1 else 200, json=response(), request=httpx.Request('POST', url))
    monkeypatch.setattr('dhaga.models.httpx.post', post)
    monkeypatch.setattr('dhaga.models.time.sleep', lambda _: None)
    assert g._jev_decide('returns', RAW).primary_reason == 'damaged'
    assert [c['status'] for c in g.calls] == ['failed', 'ok']

@pytest.mark.parametrize('status', [401, 402, 403, 404, 422])
def test_systemic_failure_stops_batch_and_never_exposes_key(monkeypatch, status):
    g = ModelGateway()
    g.live = True
    monkeypatch.setenv('TYPESAFE_API_KEY', 'DO_NOT_PRINT_THIS_KEY')
    monkeypatch.setenv('MODEL_A_INPUT_USD_PER_MILLION', '.042')
    monkeypatch.setenv('MODEL_A_OUTPUT_USD_PER_MILLION', '0')
    def post(url, **kwargs):
        return httpx.Response(status, json={'error': 'DO_NOT_PRINT_THIS_KEY'}, request=httpx.Request('POST', url))
    monkeypatch.setattr('dhaga.models.httpx.post', post)
    results = process([RAW, {**RAW, 'message_id': 'M2'}], 'returns', g, {'S1'})
    assert len(g.calls) == 1
    assert f'HTTP {status}' in results[0]['error']
    assert results[1]['error'].startswith('Not attempted')
    assert 'DO_NOT_PRINT_THIS_KEY' not in str(results) + str(g.calls)
    assert g.usage()[0]['estimated_usd'] is None


def test_invalid_response_stops_without_repeating_paid_call(monkeypatch):
    g = ModelGateway()
    g.live = True
    monkeypatch.setenv('TYPESAFE_API_KEY', 'fake')
    body = response()
    del body['answers']['primary']
    def post(url, **kwargs):
        return httpx.Response(200, json=body, request=httpx.Request('POST', url))
    monkeypatch.setattr('dhaga.models.httpx.post', post)
    results = process([RAW, {**RAW, 'message_id': 'M2'}], 'returns', g, {'S1'})
    assert len(g.calls) == 1 and g.calls[0]['usage_known']
    assert 'could not be validated' in results[0]['error']
    assert results[1]['error'].startswith('Not attempted')
