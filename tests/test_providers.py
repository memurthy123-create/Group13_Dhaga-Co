import httpx
import pytest
from dhaga.models import ModelGateway
from dhaga.errors import capture_error, ModelFailure

@pytest.mark.parametrize('provider,model,key,endpoint', [
 ('deepseek','deepseek-flash','DEEPSEEK_API_KEY','https://api.deepseek.com/chat/completions'),
 ('openrouter','deepseek/deepseek-v4.1-flash','OPENROUTER_API_KEY','https://openrouter.ai/api/v1/chat/completions')])
def test_provider_selects_correct_endpoint_key_and_validates_json(monkeypatch, provider, model, key, endpoint):
    monkeypatch.setenv('MODEL_A_PROVIDER', provider)
    monkeypatch.setenv('MODEL_A', model)
    monkeypatch.setenv(key, 'provider-test-key')
    g=ModelGateway()
    g.validate_provider_a()
    def post(url, **kwargs):
        assert url == endpoint and kwargs['headers']['Authorization'] == 'Bearer provider-test-key'
        assert kwargs['json']['response_format'] == {'type':'json_object'}
        from dhaga.schemas import ReturnDecision
        decision=ReturnDecision(primary_reason='damaged',secondary_reasons=[],evidence='torn',confidence=.95,needs_review=False,explanation='damage stated')
        return httpx.Response(200, request=httpx.Request('POST',url), json={
          'choices':[{'message':{'content':decision.model_dump_json()}}],
          'usage':{'prompt_tokens':40,'completion_tokens':10}, 'model':model})
    monkeypatch.setattr('dhaga.models.httpx.post', post)
    assert g._chat_decide('returns', {'text':'torn'}).primary_reason == 'damaged'
    assert g.calls[0]['provider'] == provider and g.calls[0]['usage_known']


def test_typesafe_rejects_deepseek_id_before_api_call(monkeypatch):
    monkeypatch.setenv('MODEL_A_PROVIDER','typesafe')
    monkeypatch.setenv('MODEL_A','deepseek/deepseek-v4.1-flash')
    with pytest.raises(ValueError,match='Jev IDs only'):
        ModelGateway().validate_provider_a()


def test_debug_prints_provider_body_and_traceback_but_redacts_key(monkeypatch, capsys):
    monkeypatch.setenv('DEBUG_ERRORS','true')
    monkeypatch.setenv('OPENROUTER_API_KEY','secret-example-key')
    response=httpx.Response(401, json={'error':'Invalid credentials secret-example-key'}, request=httpx.Request('POST','https://openrouter.ai/api/v1/chat/completions'))
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        output=capture_error(exc,'OpenRouter')
    assert 'Traceback' in output and 'Invalid credentials' in output and 'HTTP status: 401' in output
    assert 'secret-example-key' not in output and '[REDACTED]' in output
    assert output in capsys.readouterr().err


def test_provider_invalid_json_not_accepted(monkeypatch):
    monkeypatch.setenv('MODEL_A_PROVIDER','deepseek')
    monkeypatch.setenv('MODEL_A','deepseek-flash')
    monkeypatch.setenv('DEEPSEEK_API_KEY','fake')
    g=ModelGateway()
    def post(url, **kwargs):
        return httpx.Response(200, request=httpx.Request('POST',url), json={'choices':[{'message':{'content':'{"wrong":"schema"}'}}]})
    monkeypatch.setattr('dhaga.models.httpx.post',post)
    with pytest.raises(ModelFailure,match='valid decision JSON'):
        g._chat_decide('returns',{'text':'torn'})
    assert g.calls[0]['status']=='failed'
