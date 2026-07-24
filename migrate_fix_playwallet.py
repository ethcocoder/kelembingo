"""One-time migration: fix play_wallet fields stored as {__type: increment, value: N} dicts.

Run: python migrate_fix_playwallet.py
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from firestore_db import SessionLocal, FirestoreDocument

sess = SessionLocal()
try:
    docs = sess.query(FirestoreDocument).filter(
        FirestoreDocument.collection == 'users'
    ).all()
    fixed = 0
    for doc in docs:
        data = json.loads(doc.data) if doc.data else {}
        changed = False
        for key in ('play_wallet', 'balance', 'bonus'):
            val = data.get(key)
            if isinstance(val, dict) and '__type' in val:
                data[key] = val.get('value', 0)
                changed = True
                print(f"  Fixed {doc.doc_id}.{key}: {val} -> {data[key]}")
        if changed:
            doc.data = json.dumps(data)
            fixed += 1
    sess.commit()
    print(f"\nFixed {fixed} user documents. Done.")
finally:
    sess.close()
