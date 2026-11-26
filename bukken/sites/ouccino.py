"""オウチーノ（o-uccino.com）— サイト自身の検索画面が使う検索 API から23区分をまとめて取得

- 区別の検索一覧ページ（/front/search/?a=...&e=l 等）は中身を JavaScript で描画し、データは
  https://search.o-uccino.jp/api/v2/estates（JSON）から読み込んでいる。同じ API を同じ条件で呼ぶ。
  （search.o-uccino.jp の robots.txt は 404 = 制限なし。o-uccino.com の robots.txt は
  /front/favorites, /front/recently, /beta, 一部の /front/estates/ID を禁止しているが、
  ここでは詳細ページを取得せず URL を記録するだけ。）
- パラメータ（サイトの JS と同じもの）:
    a=<区コード,…>  e=l（土地）/ n,h（新築一戸建て）/ u,h（中古一戸建て）
    p=..<上限万円>  size=<件数>  page=<N>  aggs=em
- 1回 500 件まで取得して、2026-11 時点で 土地 837件・新築 1948件・中古 1309件 → 計 9 リクエスト程度。
- 区・価格・種別はモジュール側でも確認する。
"""
import json
import math

from .. import config
from ..common import Listing, fetch, norm, parse_walk, ward_of

NAME = "オウチーノ"
BASE = "https://o-uccino.com"
API = "https://search.o-uccino.jp/api/v2/estates"
SIZE = 500
TYPES = [  # (e, 種類, 価格上限, 期待する (type, division))
    ("l", "土地", config.LAND_MAX_MAN, ("land", None)),
    ("n,h", "新築戸建", config.TOTAL_MAX_MAN, ("house", "new")),
    ("u,h", "中古戸建", config.TOTAL_MAX_MAN, ("house", "used")),
]


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _price_text(c: dict) -> str:
    lo, hi = _num(c.get("price_min")), _num(c.get("price_max"))
    if lo is None:
        return "価格未定"
    fmt = lambda v: f"{int(v):,}万円" if v == int(v) else f"{v:,}万円"
    return fmt(lo) + (f"～{fmt(hi)}" if hi and hi > lo else "")


def _to_listing(x: dict, kind: str, limit: float, want: tuple) -> Listing | None:
    ident, loc = x.get("identifier", {}), x.get("location", {})
    fac, cost = x.get("facility", {}) or {}, x.get("cost", {}) or {}
    typ, div = want
    if ident.get("type") != typ or (div and ident.get("division") != div):
        return None
    address = norm(loc.get("full_address") or (loc.get("city_name", "") + loc.get("address", "")))
    if not ward_of(address):
        return None
    price = _num(cost.get("price_min"))
    if price is not None and price > limit:
        return None
    routes = [norm(t.get("route", "")) for t in x.get("traffics") or [] if t.get("route")]
    access = " / ".join(routes)
    walks = [t.get("walk_time_station") for t in x.get("traffics") or []
             if not t.get("ride_time_bus") and t.get("walk_time_station")]
    walk = min(walks) if walks else parse_walk(access)
    extra = [norm(fac.get("caption", ""))]
    extra += fac.get("floor_plans") or []
    if fac.get("built_years") and kind != "土地":
        extra.append(("築" if kind == "中古戸建" else "完成") + str(fac["built_years"]))
    if fac.get("total_floor_number"):
        extra.append(f"{fac['total_floor_number']}階建")
    if fac.get("home_construction_required"):
        extra.append("建築条件付き")
    if fac.get("is_reform") or fac.get("is_renovation"):
        extra.append("リフォーム済")
    if fac.get("build_plan"):
        extra.append(norm(fac["build_plan"]))
    eid = ident.get("id", "")
    return Listing(
        site=NAME, id=eid, kind=kind, title=norm(ident.get("name", "")),
        url=f"{BASE}/front/estates/{eid}/",
        price_text=_price_text(cost), price_man=price,
        address=address, access=access, walk_min=walk,
        land_m2=_num(fac.get("land_area_min")), building_m2=_num(fac.get("building_area_min")),
        kenpei=_num(fac.get("building_coverage_ratio")), yoseki=_num(fac.get("floor_space_ratio")),
        extra=" ".join(e for e in extra if e)[:400],
    )


def _url(e: str, limit: float, page: int, wards: str) -> str:
    return f"{API}?a={wards}&e={e}&p=..{int(limit)}&aggs=em&size={SIZE}" + (f"&page={page}" if page > 1 else "")


def collect(log=print) -> list[Listing]:
    wards = ",".join(c for c, _, _ in config.WARDS)
    res, seen = [], set()
    for e, kind, limit, want in TYPES:
        page, pages, total, n = 1, 1, 0, 0
        while page <= pages:
            d = json.loads(fetch(_url(e, limit, page, wards)))
            total = int(d.get("total") or 0)
            pages = min(max(1, math.ceil(total / SIZE)), 20)
            for x in d.get("estates") or []:
                li = _to_listing(x, kind, limit, want)
                if li and li.id not in seen:
                    seen.add(li.id)
                    res.append(li)
                    n += 1
            page += 1
        log(f"  {NAME} {kind} 23区: {total}件（{pages}ページ）→ {n}件")
    return res
