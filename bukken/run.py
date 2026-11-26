"""毎日実行する本体。

  python -m bukken.run            全サイトを取得 → 判定 → 新着を記録 → レポート作成
  python -m bukken.run --sites suumo,homes   一部のサイトだけ
"""
import argparse
import datetime as dt
import json
import sys
import time
import traceback
from pathlib import Path

from .common import Blocked
from .evaluate import evaluate
from .report import write_report
from .sites import all_sites

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
JST = dt.timezone(dt.timedelta(hours=9))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", help="カンマ区切りのモジュール名")
    ap.add_argument("--out", default=str(ROOT / "report" / "index.html"))
    args = ap.parse_args()

    today = dt.datetime.now(JST).strftime("%Y-%m-%d")
    seen_path = DATA / "seen.json"
    seen: dict[str, dict] = json.loads(seen_path.read_text()) if seen_path.exists() else {}
    first_run = not seen

    status, candidates = [], []
    mods = all_sites()
    if args.sites:
        want = set(args.sites.split(","))
        mods = [m for m in mods if m.__name__.rsplit(".", 1)[-1] in want]
    for mod in mods:
        t0 = time.time()
        print(f"[{mod.NAME}] 取得開始", flush=True)
        try:
            items = mod.collect(log=lambda s: print(s, flush=True))
            uniq = {i.key: i for i in items}
            ok = [x for x in (evaluate(i) for i in uniq.values()) if x]
            candidates.extend(ok)
            status.append({"site": mod.NAME, "ok": True, "fetched": len(uniq), "candidates": len(ok),
                           "sec": round(time.time() - t0)})
            print(f"[{mod.NAME}] {len(uniq)}件取得 / 候補{len(ok)}件", flush=True)
        except Exception as e:  # 1サイトの失敗で全体を止めない
            msg = str(e) if isinstance(e, Blocked) else f"{type(e).__name__}: {e}"
            traceback.print_exc()
            status.append({"site": mod.NAME, "ok": False, "error": msg[:200], "sec": round(time.time() - t0)})

    # 新着判定
    rows = []
    for l in candidates:
        d = l.to_dict()
        prev = seen.get(l.key)
        if prev is None:
            d["first_seen"] = today
            d["price_change"] = None
        else:
            d["first_seen"] = prev["first_seen"]
            old = prev.get("price_man")
            d["price_change"] = (l.price_man - old) if (old and l.price_man and l.price_man != old) else None
        seen[l.key] = {"first_seen": d["first_seen"], "last_seen": today, "price_man": l.price_man}
        rows.append(d)

    DATA.mkdir(exist_ok=True)
    seen_path.write_text(json.dumps(seen, ensure_ascii=False, indent=0, sort_keys=True))
    (DATA / "latest.json").write_text(json.dumps(
        {"date": today, "first_run": first_run, "status": status, "rows": rows}, ensure_ascii=False))
    write_report(Path(args.out), today, first_run, status, rows)
    new = sum(1 for r in rows if r["first_seen"] == today)
    print(f"完了: 候補{len(rows)}件 / 新着{new}件 → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
