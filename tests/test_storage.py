from dhaga.storage import SupabaseStore
from dhaga.workflows import process, review
from dhaga.models import ModelGateway

class FakeClient:
    def __init__(self): self.operations=[]
    def table(self,name): self.operations.append(('table',name)); return self
    def upsert(self,payload,on_conflict): self.operations.append(('upsert',payload,on_conflict)); return self
    def rpc(self,name,params): self.operations.append(('rpc',name,params)); return self
    def execute(self): return self

def test_supabase_upsert_and_atomic_review_payload():
    store=object.__new__(SupabaseStore); store.client=FakeClient()
    raw=dict(message_id='M1', source='app', case_id='C1',order_id='O1',sku='S1',text='The top arrived torn')
    record=process([raw],'returns',ModelGateway(),{'S1'})[0]
    store.save([record])
    assert store.client.operations[0]==('table','return_records')
    payload=store.client.operations[1][1][0]
    assert payload['raw']==raw and 'task' not in payload
    corrected=review(record,record['decision'],'Neha','Confirmed')
    store.save_review(record,corrected)
    call=store.client.operations[-1]
    assert call[0]=='rpc' and call[1]=='save_dhaga_review'
    assert call[2]['p_before']==record['decision']
    assert call[2]['p_record']['reviewed_by']=='Neha'
