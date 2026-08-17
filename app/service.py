from __future__ import annotations
import asyncio
import hashlib
import hmac
import logging
import time
import uuid
from typing import Optional

from .config import Settings
from .db import Database
from .pseudogram import PseudoGramClient

log = logging.getLogger(__name__)

class LinkPleaseService:
    def __init__(self, db: Database, client: PseudoGramClient, settings: Settings):
        self.db = db
        self.client = client
        self.settings = settings
        self.stop_event = asyncio.Event()
        self.worker_task: Optional[asyncio.Task] = None
        self.worker_lock = asyncio.Lock()

    def verify_signature(self, raw_body: bytes, signature: Optional[str]) -> bool:
        if not signature:
            return not self.settings.require_webhook_signature
        if not signature.startswith("sha256="):
            return False
        supplied = signature[7:]
        expected = hmac.new(self.settings.pseudogram_api_key.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, supplied)

    def create_rule(self, keyword: str, dm_message: str) -> dict:
        keyword = keyword.strip()
        if not keyword:
            raise ValueError("keyword cannot be empty")
        rule_id = f"rule_{uuid.uuid4().hex}"
        now = time.time()
        with self.db.transaction() as c:
            c.execute("INSERT INTO rules(rule_id,keyword,keyword_normalized,dm_message,created_at) VALUES(?,?,?,?,?)",
                      (rule_id, keyword, keyword.casefold(), dm_message, now))
        return {"rule_id": rule_id, "keyword": keyword, "dm_message": dm_message}

    def ingest_event(self, event: dict) -> str:
        now = time.time()
        event_id = event["event_id"]
        event_type = event["event_type"]
        data = event["data"]
        comment_id = data["comment_id"]
        user = data.get("from") or {}
        user_id = user.get("user_id")
        text = data.get("text")
        with self.db.transaction() as c:
            existing = c.execute("SELECT 1 FROM events WHERE event_id=?", (event_id,)).fetchone()
            if existing:
                return "duplicate_event"
            c.execute("INSERT INTO events(event_id,event_type,comment_id,received_at) VALUES(?,?,?,?)",
                      (event_id,event_type,comment_id,now))
            if event_type == "comment.deleted":
                c.execute("UPDATE comments SET deleted_at=? WHERE comment_id=?", (now, comment_id))
                c.execute("UPDATE deliveries SET status='cancelled', updated_at=?, last_error='comment_deleted_before_delivery' WHERE comment_id=? AND status='queued'",
                          (now, comment_id))
                return "deleted"
            c.execute("INSERT INTO comments(comment_id,user_id,text,post_id,created_at) VALUES(?,?,?,?,?) ON CONFLICT(comment_id) DO UPDATE SET user_id=excluded.user_id,text=excluded.text,post_id=excluded.post_id",
                      (comment_id,user_id,text,data.get("post_id"),now))
            if not user_id or not text:
                return "ignored"
            rules = c.execute("SELECT rule_id,keyword,keyword_normalized,dm_message FROM rules").fetchall()
            matched = 0
            for rule in rules:
                if rule["keyword_normalized"] in text.casefold():
                    matched += 1
                    delivery_id = f"dlv_{uuid.uuid4().hex}"
                    idem = f"{rule['rule_id']}:{user_id}"
                    try:
                        c.execute("INSERT INTO deliveries(delivery_id,rule_id,user_id,comment_id,message,status,attempts,idempotency_key,next_attempt_at,last_error,created_at,updated_at) VALUES(?,?,?,?,?,'queued',0,?,?,NULL,?,?)",
                                  (delivery_id,rule["rule_id"],user_id,comment_id,rule["dm_message"],idem,now,now,now))
                    except Exception as exc:
                        if "UNIQUE constraint failed: deliveries.rule_id, deliveries.user_id" in str(exc):
                            c.execute("SELECT 1 FROM deliveries WHERE rule_id=? AND user_id=?", (rule["rule_id"],user_id))
                            # This is an intentional duplicate block, not an error.
                            c.execute("INSERT OR IGNORE INTO events(event_id,event_type,comment_id,received_at) VALUES(?,?,?,?)", (f"duplicate-block:{event_id}:{rule['rule_id']}:{user_id}", "duplicate_blocked", comment_id, now))
                        else:
                            raise
            return "matched" if matched else "no_match"

    def _claim_due(self) -> Optional[dict]:
        now = time.time()
        with self.db.transaction() as c:
            row = c.execute("SELECT * FROM deliveries WHERE status='queued' AND next_attempt_at<=? ORDER BY next_attempt_at,created_at LIMIT 1", (now,)).fetchone()
            if not row:
                return None
            c.execute("UPDATE deliveries SET status='sending',updated_at=? WHERE delivery_id=? AND status='queued'", (now,row["delivery_id"]))
            return dict(row)

    def _rate_limit_wait(self) -> float:
        now = time.time()
        cutoff = now - 60.0
        with self.db.transaction() as c:
            c.execute("DELETE FROM send_window WHERE sent_at<?", (cutoff,))
            row = c.execute("SELECT COUNT(*) AS n, MIN(sent_at) AS oldest FROM send_window").fetchone()
            if row["n"] < 10:
                c.execute("INSERT INTO send_window(sent_at) VALUES(?)", (now,))
                return 0.0
            return max(0.05, row["oldest"] + 60.0 - now)

    def _set_retry(self, delivery_id: str, attempts: int, delay: float, error: str):
        now = time.time()
        with self.db.transaction() as c:
            c.execute("UPDATE deliveries SET status='queued',attempts=?,next_attempt_at=?,last_error=?,updated_at=? WHERE delivery_id=?",
                      (attempts,now+delay,error,now,delivery_id))

    def _set_accepted(self, delivery_id: str, attempts: int, dm_id: str):
        now=time.time()
        with self.db.transaction() as c:
            c.execute("UPDATE deliveries SET status='accepted',attempts=?,dm_id=?,next_attempt_at=?,last_error=NULL,updated_at=? WHERE delivery_id=?",
                      (attempts,dm_id,now+self.settings.reconcile_after_seconds,now,delivery_id))

    def _set_terminal(self, delivery_id: str, status: str, error: str | None = None):
        now=time.time()
        with self.db.transaction() as c:
            c.execute("UPDATE deliveries SET status=?,last_error=?,updated_at=? WHERE delivery_id=?", (status,error,now,delivery_id))

    def _set_reconcile_due(self) -> Optional[dict]:
        now=time.time()
        with self.db.transaction() as c:
            row=c.execute("SELECT * FROM deliveries WHERE status='accepted' AND next_attempt_at<=? ORDER BY next_attempt_at LIMIT 1",(now,)).fetchone()
            if row:
                c.execute("UPDATE deliveries SET next_attempt_at=?,updated_at=? WHERE delivery_id=?",(now+30,now,row["delivery_id"]))
                return dict(row)
        return None

    async def _process_delivery(self, row: dict):
        wait=self._rate_limit_wait()
        if wait:
            self._set_retry(row["delivery_id"], row["attempts"], wait, "local_rate_limiter")
            return
        attempts=row["attempts"]+1
        result=await self.client.send_dm(row["user_id"],row["message"],row["comment_id"],row["idempotency_key"])
        if result.kind == "accepted":
            self._set_accepted(row["delivery_id"],attempts,result.dm_id)
            return
        if result.kind == "permanent":
            self._set_terminal(row["delivery_id"],"failed",result.error)
            return
        if attempts >= self.settings.max_retries:
            self._set_terminal(row["delivery_id"],"failed",result.error or "retry_exhausted")
            return
        delay=result.retry_after or min(60.0,self.settings.retry_base_seconds*(2**(attempts-1)))
        self._set_retry(row["delivery_id"],attempts,delay,result.error or "retryable_error")

    async def _process_reconciliation(self,row:dict):
        result=await self.client.get_dm(row["dm_id"])
        if result.kind == "ok":
            if result.status == "delivered":
                self._set_terminal(row["delivery_id"],"delivered")
            elif result.status == "failed":
                # A failed accepted DM needs a fresh idempotency key for a new attempt.
                if row["attempts"] >= self.settings.max_retries:
                    self._set_terminal(row["delivery_id"],"failed","delivery_failed_after_reconciliation")
                else:
                    now=time.time()
                    with self.db.transaction() as c:
                        c.execute("UPDATE deliveries SET status='queued',idempotency_key=?,next_attempt_at=?,last_error=?,updated_at=? WHERE delivery_id=?",
                                  (f"{row['delivery_id']}:{row['attempts']+1}",now+min(60,self.settings.retry_base_seconds*(2**max(0,row['attempts']-1))),"accepted_but_later_failed",now,row["delivery_id"]))
            else:
                now=time.time()
                with self.db.transaction() as c:
                    c.execute("UPDATE deliveries SET next_attempt_at=?,updated_at=? WHERE delivery_id=?",(now+2,now,row["delivery_id"]))
        else:
            now=time.time()
            with self.db.transaction() as c:
                c.execute("UPDATE deliveries SET next_attempt_at=?,updated_at=?,last_error=? WHERE delivery_id=?",(now+10,now,result.error,row["delivery_id"]))

    async def worker_loop(self):
        while not self.stop_event.is_set():
            did=False
            row=self._set_reconcile_due()
            if row:
                did=True
                await self._process_reconciliation(row)
                continue
            row=self._claim_due()
            if row:
                did=True
                try:
                    await self._process_delivery(row)
                except Exception as exc:
                    log.exception("delivery worker error")
                    attempts=row["attempts"]+1
                    if attempts >= self.settings.max_retries:
                        self._set_terminal(row["delivery_id"],"failed",f"worker_exception:{exc}")
                    else:
                        self._set_retry(row["delivery_id"],attempts,min(60,self.settings.retry_base_seconds*(2**(attempts-1))),f"worker_exception:{type(exc).__name__}")
            if not did:
                await asyncio.sleep(self.settings.worker_poll_seconds)

    async def start(self):
        self.stop_event.clear()
        self.worker_task=asyncio.create_task(self.worker_loop())

    async def stop(self):
        self.stop_event.set()
        if self.worker_task:
            try: await asyncio.wait_for(self.worker_task, timeout=5)
            except asyncio.TimeoutError: self.worker_task.cancel()
        await self.client.close()

    def stats(self) -> dict:
        with self.db.connect() as c:
            rows=c.execute("SELECT status,COUNT(*) AS n FROM deliveries GROUP BY status").fetchall()
            counts={r["status"]:r["n"] for r in rows}
            duplicate=c.execute("SELECT COUNT(*) AS n FROM events WHERE event_type='duplicate_blocked'").fetchone()["n"]
            return {"sent":counts.get("delivered",0),"failed":counts.get("failed",0),"queued":sum(counts.get(s,0) for s in ("queued","sending","accepted")),"duplicates_blocked":duplicate}
