from __future__ import annotations
import os, datetime
from pymongo import MongoClient

def get_mongo():
    cli = MongoClient(os.getenv("MONGO_URI"))
    return cli[os.getenv("MONGO_DB", "ledgermate")]

def save_raw_policy(org_id: str, version: str, source_name: str, raw_json: dict) -> str:
    db = get_mongo()
    doc = {
        "type": "policy_parse",
        "org_id": org_id,
        "version": version,
        "source_name": source_name,
        "raw": raw_json,
        "created_at": datetime.datetime.utcnow(),
    }
    res = db.document_raw.insert_one(doc)
    return str(res.inserted_id)