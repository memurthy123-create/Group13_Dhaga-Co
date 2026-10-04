import io
from types import SimpleNamespace
import pandas as pd
import pytest
from dhaga.models import ModelGateway
from dhaga.rules import standardise_rules
from dhaga.workflows import read_input, process, review, csv_export


def message(text='The top is tight', **kw):
    return dict(message_id='M1',source='app',case_id='C1',order_id='O1',sku='S1',text=text,**kw)

def test_negation_is_not_silently_accepted():
    r=process([message('It is not tight, it arrived torn')], 'returns', ModelGateway(), {'S1'})[0]
    assert r['status']=='needs_review'

def test_unknown_sku_and_blank_text_need_review():
    r=process([message('')], 'returns', ModelGateway(), set())[0]
    assert r['status']=='needs_review'
    assert r['decision']['primary_reason']=='insufficient_information'

def test_nonreturn_tracking_enquiry():
    r=process([message('Where is my order?')], 'returns', ModelGateway(), {'S1'})[0]
    assert r['decision']['primary_reason']=='not_return'

def test_preserve_vendor_sizes_shades_and_blend():
    raw=dict(sku='S1',vendor_id='V1',product_name='Top',colour_raw='navy blue',fabric_raw='60% cotton / 40% polyester',size_raw='38',size_chart_id='C1',chest_cm='91')
    r=process([raw],'catalogue',ModelGateway())[0]
    assert r['decision']['colour_family']=='Blue'
    assert r['decision']['colour_shade']=='Navy'
    assert r['decision']['fabric']=='Blend'
    assert r['decision']['size_label']=='Vendor Specific'
    assert r['raw']['chest_cm']=='91'
    assert r['status']=='needs_review'

def test_duplicate_ids_rejected():
    data=pd.DataFrame([message(),message()]).to_csv(index=False)
    with pytest.raises(ValueError,match='Duplicate'):
        read_input(io.StringIO(data),'returns')

def test_missing_columns_rejected():
    with pytest.raises(ValueError,match='Missing columns'):
        read_input(io.StringIO('message_id,text\nM1,hello'),'returns')

def test_gateway_failure_visible():
    class Broken:
        live=True
        def decide(self,*a,**kw): raise RuntimeError('timeout')
    r=process([message()],'returns',Broken(),{'S1'})[0]
    assert r['status']=='failed' and r['decision'] is None and r['error']

def test_human_correction_keeps_original():
    r=process([message('Bad')],'returns',ModelGateway(),{'S1'})[0]
    decision={**r['decision'],'primary_reason':'damaged'}
    fixed=review(r,decision,'Neha','Inspected photo manually')
    assert fixed['status']=='approved'
    assert fixed['raw']==r['raw']
    assert fixed['previous_decision']==r['decision']
    with pytest.raises(ValueError): review(r,decision,'','')

def test_formula_export_escaped():
    result=csv_export(pd.DataFrame({'text':['=1+1','safe']})).decode('utf-8-sig')
    assert "'=1+1" in result

def test_two_model_chaining_and_disagreement_routes_to_human():
    from dhaga.schemas import ReturnDecision
    class Gateway:
        live=True
        def __init__(self): self.previous=[]
        def decide(self, task, raw, previous=None):
            self.previous.append(previous)
            return ReturnDecision(primary_reason='damaged' if previous else 'other',secondary_reasons=[],evidence=raw['text'],confidence=.9,needs_review=not bool(previous),explanation='review')
    g=Gateway(); r=process([message()],'returns',g,{'S1'})[0]
    assert len(g.previous)==2 and g.previous[1] is not None
    assert r['status']=='needs_review' and r['reviewer_used']

def test_structured_model_retry_and_token_logging():
    from dhaga.schemas import ReturnDecision
    gateway=ModelGateway()
    gateway.live=True
    result=ReturnDecision(primary_reason='damaged',secondary_reasons=[],evidence='torn',confidence=.9,needs_review=False,explanation='stated damage')
    class FakeCompletions:
        count=0
        def parse(self, **kwargs):
            self.count+=1
            assert kwargs['response_format'] is ReturnDecision
            assert kwargs['temperature']==0
            if self.count==1: raise ValueError('invalid')
            return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=10,completion_tokens=5),choices=[SimpleNamespace(message=SimpleNamespace(parsed=result))])
    gateway.client=SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    assert gateway.decide('returns',{'text':'torn'}, previous={'primary_reason':'other'}).primary_reason=='damaged'
    assert len(gateway.calls)==2 and gateway.calls[1]['input_tokens']==10
