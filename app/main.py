from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse

from .config import settings
from .db import Database
from .models import RuleCreate, RuleResponse, StatsResponse
from .pseudogram import PseudoGramClient
from .service import LinkPleaseService

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s %(message)s")

db=Database(settings.database_path)
client=PseudoGramClient(settings.pseudogram_base_url, settings.pseudogram_api_key)
service=LinkPleaseService(db,client,settings)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await service.start()
    yield
    await service.stop()

app=FastAPI(title="LinkPlease Comment-to-DM Automation", version="1.0.0", lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status":"ok"}

@app.post("/rules",response_model=RuleResponse,status_code=status.HTTP_201_CREATED)
async def create_rule(body: RuleCreate):
    try:
        return service.create_rule(body.keyword,body.dm_message)
    except ValueError as exc:
        raise HTTPException(400,str(exc))

@app.post("/webhook")
async def webhook(request: Request):
    raw=await request.body()
    signature = request.headers.get("X-PseudoGram-Signature")
    if service.settings.require_webhook_signature:
        if not service.verify_signature(raw, signature):
            raise HTTPException(status_code=401, detail="invalid webhook signature")
    try:
        event=await request.json()
    except Exception:
        raise HTTPException(status_code=400,detail="invalid JSON")
    required=("event_id","event_type","data")
    if any(k not in event for k in required):
        raise HTTPException(status_code=400,detail="invalid event")
    try:
        service.ingest_event(event)
    except Exception:
        # Do not acknowledge persistence failures: the sender can safely retry.
        raise HTTPException(status_code=503,detail="event could not be persisted")
    return JSONResponse({"ok":True},status_code=200)

@app.get("/stats",response_model=StatsResponse)
async def stats():
    return service.stats()
