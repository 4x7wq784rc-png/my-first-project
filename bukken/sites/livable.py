"""東急リバブル（区ごとの一覧ページ。Next.js の __NEXT_DATA__ に入った物件一覧を読む）

使うURL（robots.txt の User-agent: * で禁止されていないもの。禁止は /kounyu/kw/*?* や /kounyu/s/map/ など）:
  /kounyu/tochi/tokyo/a<区コード>/?sort=price_low_to_high&page=<n>    土地
  /kounyu/kodate/tokyo/a<区コード>/?sort=price_low_to_high&page=<n>   一戸建て（新築・中古が混在）
価格の上限指定（price-to）はURLパラメータでは効かないため、価格の安い順に並べて取得し、
上限を超える物件が出たらそこで次の区へ進む（リクエスト数を抑えるため）。
"""
import json
import math
import re

from .. import config
from ..common import Blocked, Listing, fetch, norm, parse_m2, parse_ratio, parse_walk

NAME = "東急リバブル"
BASE = "https://www.livable.co.jp"
TYPES = [  # (URLの種別, 価格上限 万円)
    ("tochi", config.LAND_MAX_MAN),
    ("kodate", config.TOTAL_MAX_MAN),
]
PER_PAGE = 30
MAX_PAGES = 30


def _get(url: str) -> str:
    path = url[len(BASE):]
    # robots.txt の「Disallow: /kounyu/kw/*?*」「/kounyu/s/map/」「/*/complete/」に当たらないことを確認
    if path.startswith(("/kounyu/kw/", "/kounyu/s/")) or "/complete/" in path:
        raise Blocked(f"robots.txt で禁止: {url}")
    return fetch(url)


def _man(yen) -> float | None:
    return round(yen / 10000, 1) if isinstance(yen, (int, float)) and yen > 0 else None


def _yen_text(man: float | None) -> str:
    if not man:
        return ""
    oku, rest = divmod(int(round(man)), 10000)
    return (f"{oku}億" if oku else "") + (f"{rest:,}万円" if rest else "円" if oku else "")


def _price(pm: dict) -> tuple[str, float | None, float | None]:
    """(表示, 下限万円, 上限万円)"""
    pm = pm or {}
    if "price" in pm:
        m = _man(pm.get("price"))
        return _yen_text(m), m, m
    lo, hi = _man(pm.get("priceFrom")), _man(pm.get("priceTo"))
    if lo or hi:
        txt = _yen_text(lo) + ("～" + _yen_text(hi) if hi and hi != lo else "")
        return txt, lo or hi, hi or lo
    return "", None, None


def _parse(html: str, path: str) -> tuple[list[Listing], int]:
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        raise Blocked("__NEXT_DATA__ が見つかりません（ページ構成変更または拒否）")
    pp = json.loads(m.group(1)).get("props", {}).get("pageProps", {})
    total = int(re.sub(r"\D", "", str(pp.get("searchedResultCounts") or "")) or 0)
    out = []
    for p in pp.get("propertyList") or []:
        cd = p.get("propertyCd")
        if not cd:
            continue
        labels = [norm(x.get("listText", "")) for x in (p.get("labelList") or []) + (p.get("otherConditionLabels") or [])
                  if isinstance(x, dict)]
        labels = [x for x in labels if x and not re.match(r"(NEW|新価格)\s*\d", x)]
        detail = [norm(re.sub(r"<[^>]+>", "", d)) for d in (p.get("propertyDetail") or []) if isinstance(d, str)]
        dtext = " / ".join(detail)
        if path == "tochi":
            kind = "土地"
        elif any("新築" in x for x in labels):
            kind = "新築戸建"
        else:
            kind = "中古戸建"
        if any(re.search(r"アパート|一棟|収益|オーナーチェンジ", x) for x in labels):
            kind = "収益・併用"
        land = next((parse_m2(d) for d in detail if d.startswith("土地")), None)
        bldg = next((parse_m2(d) for d in detail if d.startswith("建物")), None)
        kp, yk = parse_ratio(dtext)
        access = " / ".join(norm(a) for a in (p.get("access") or []) if isinstance(a, str))
        price_text, lo, _ = _price(p.get("priceModel"))
        url = p.get("detailUrl") or f"/{path}/{cd}/"
        out.append(Listing(
            site=NAME, id=cd, kind=kind,
            title=norm(p.get("propertyName") or p.get("address") or ""),
            url=url if url.startswith("http") else BASE + url,
            price_text=price_text, price_man=lo,
            address=norm(p.get("address") or ""), access=access, walk_min=parse_walk(access),
            land_m2=land, building_m2=bldg, kenpei=kp, yoseki=yk,
            extra=" ".join(x for x in [d for d in detail if not re.match(r"(土地|建物|建ぺい率|容積率)", d)] + labels if x),
        ))
    return out, max(1, math.ceil(total / PER_PAGE))


def collect(log=print) -> list[Listing]:
    res = []
    for path, max_man in TYPES:
        for code, _, wname in config.WARDS:
            page, pages, n = 1, 1, 0
            while page <= min(pages, MAX_PAGES):
                url = f"{BASE}/kounyu/{path}/tokyo/a{code}/?sort=price_low_to_high"
                if page > 1:
                    url += f"&page={page}"
                items, pages = _parse(_get(url), path)
                ok = [i for i in items if i.price_man is not None and i.price_man <= max_man]
                res.extend(ok)
                n += len(ok)
                # 安い順なので、上限超えが出たら以降のページは不要
                if any(i.price_man is not None and i.price_man > max_man for i in items):
                    break
                page += 1
            log(f"  リバブル {path} {wname}: {n}件")
    return res
