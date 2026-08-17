import hashlib,hmac,json,time
from pathlib import Path
from app.config import Settings
from app.db import Database
from app.service import LinkPleaseService

class DummyClient: pass

def make_service(tmp_path):
    s=Settings(database_path=str(tmp_path/"test.db"),pseudogram_api_key="secret",require_webhook_signature=True)
    return LinkPleaseService(Database(s.database_path),DummyClient(),s)

def event(eid,user,text,cid=None,etype="comment.created"):
    return {"event_id":eid,"event_type":etype,"data":{"comment_id":cid or eid,"text":text,"from":{"user_id":user,"username":"x"}}}

def test_rule_matching_and_atomic_duplicate_block(tmp_path):
    svc=make_service(tmp_path)
    svc.create_rule("PRICE","price list")
    svc.ingest_event(event("e1","u1","please PRICE"))
    svc.ingest_event(event("e2","u1","PRICE again"))
    svc.ingest_event(event("e3","u2","no match"))
    assert svc.stats()["queued"]==1
    assert svc.stats()["duplicates_blocked"]==1

def test_event_redelivery_is_idempotent(tmp_path):
    svc=make_service(tmp_path)
    svc.create_rule("PRICE","price list")
    e=event("same","u1","PRICE")
    assert svc.ingest_event(e)=="matched"
    assert svc.ingest_event(e)=="duplicate_event"
    assert svc.stats()["queued"]==1

def test_deleted_comment_cancels_queued_delivery(tmp_path):
    svc=make_service(tmp_path)
    svc.create_rule("PRICE","price list")
    svc.ingest_event(event("e1","u1","PRICE",cid="c1"))
    svc.ingest_event(event("e2","u1",None,cid="c1",etype="comment.deleted"))
    assert svc.stats()["queued"]==0

def test_signature_verification(tmp_path):
    svc=make_service(tmp_path)
    raw=b'{"event_id":"x"}'
    sig="sha256="+hmac.new(b"secret",raw,hashlib.sha256).hexdigest()
    assert svc.verify_signature(raw,sig)
    assert not svc.verify_signature(raw,"sha256=bad")
