#!/usr/bin/env python3
"""Deep debug script for taken-cartela polling. Tests the REST API directly."""
import argparse, json, urllib.parse, urllib.request, urllib.error

DEFAULT_URL = "https://kelem-bingo-api.onrender.com"

def fetch_json(base, path):
    url = base + path
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"detail": body.decode(errors="replace")}

def _docs(data):
    """Extract list of {id, data} from any response format."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "documents" in data:
        return data["documents"]
    if isinstance(data, dict) and "id" in data:
        return [data]
    return []

def _id(d):
    return d["id"] if isinstance(d, dict) else str(d)

def _dat(d):
    if isinstance(d, dict):
        dd = d.get("data")
        return dd if isinstance(dd, dict) else d
    return {}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", "-r", help="Round ID to inspect")
    parser.add_argument("--url", "-u", default=DEFAULT_URL)
    args = parser.parse_args()
    BASE = args.url.rstrip("/")
    print(f"\n{'='*60}")
    print(f"TAKEN-CARTELA DEEP DEBUG — {BASE}")
    print(f"{'='*60}\n")

    # ── Step 1: Find active rounds ──
    print("1) Query active rounds (status in [selecting, playing])...")
    filt = urllib.parse.quote(json.dumps([["status", "in", ["selecting", "playing"]]]))
    s1, d1 = fetch_json(BASE, f"/api/db/rounds?filters={filt}")
    print(f"   HTTP {s1}")
    docs1 = _docs(d1)
    print(f"   Found {len(docs1)} result(s)")
    for doc in docs1:
        rid = _id(doc)
        rd = _dat(doc)
        tc = rd.get("taken_cartelas", [])
        print(f"     Round {rid}: status={rd.get('status')} "
              f"players={len(rd.get('players',{}))} "
              f"taken={len(tc)} {tc[:10]}")

    # ── Step 2: Resolve round ID ──
    round_id = args.round
    if not round_id:
        s2, d2 = fetch_json(BASE, "/api/db/rounds?filters=" + urllib.parse.quote(json.dumps([["status", "==", "selecting"]])))
        if s2 == 200:
            docs2 = _docs(d2)
            if docs2:
                round_id = _id(docs2[0])
                print(f"\n   Auto-selected round: {round_id}")
    print(f"\n   Using round_id = {round_id or 'NONE'}")

    # ── Step 3: Direct document GET ──
    print("\n2) Direct document GET /api/db/rounds/{id}...")
    if round_id:
        s3, d3 = fetch_json(BASE, f"/api/db/rounds/{round_id}")
        print(f"   HTTP {s3}")
        if s3 == 200:
            rd3 = d3.get("data", {})
            tc3 = rd3.get("taken_cartelas", [])
            print(f"   [OK] status={rd3.get('status')}")
            print(f"   [OK] player_count={rd3.get('player_count')}")
            print(f"   [OK] taken_cartelas({len(tc3)}): {tc3}")
            print(f"   [OK] players={list(rd3.get('players',{}).keys())}")
            print(f"   [OK] created_at={rd3.get('created_at')}")
        else:
            print(f"   ERROR {d3}")
    else:
        print("   ERROR No round ID — cannot fetch")

    # ── Step 4: Cartelas master ──
    print("\n3) Cartelas master count...")
    s4, d4 = fetch_json(BASE, "/api/db/cartelas_master?order_by=number&order_dir=ASCENDING")
    docs4 = _docs(d4)
    print(f"   HTTP {s4}, {len(docs4)} cartelas" if s4 == 200 else f"   ERROR {d4}")

    # ── Summary ──
    print(f"\n{'='*60}")
    if round_id and s3 == 200 and len(tc3) > 0:
        print("   taken_cartelas HAS DATA — the polling SHOULD detect these.")
        print("   If the page shows no TAKEN marks, the client-side polling")
        print("   is not running. Check the debug bar visible on the page.")
    elif round_id and s3 == 200 and len(tc3) == 0:
        print("   taken_cartelas is EMPTY — no player has confirmed yet.")
        print("   Open a second device, confirm a cartela, then re-run.")
    else:
        print("   Could not complete analysis.")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
