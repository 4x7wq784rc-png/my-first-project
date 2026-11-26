"""三井のリハウス（区ごとの一覧ページ。サーバー描画HTMLに埋め込まれた __NUXT_DATA__ を読む）

使うURL（robots.txt の User-agent: * で禁止されていないもの）:
  /buy/tochi/prefecture/13/city/<区コード>/?maxPrice=<万円>&page=<n>    土地
  /buy/kodate/prefecture/13/city/<区コード>/?maxPrice=<万円>&page=<n>   一戸建て（新築・中古・一棟アパートが混在）
robots.txt で禁止の /toushi/*, /investmentBukkenList/*, */inquiry/*, */unit/* などは使わない。
"""
import json
import re

from .. import config
from ..common import Blocked, Listing, fetch, norm, parse_m2, parse_ratio, parse_walk

NAME = "三井のリハウス"
BASE = "https://www.rehouse.co.jp"
TYPES = [  # (URLの種別, 価格上限 万円)
    ("tochi", config.LAND_MAX_MAN),
    ("kodate", config.TOTAL_MAX_MAN),
]
MAX_PAGES = 30  # 念のための上限（1ページ30件）

# robots.txt（User-agent: *）の禁止パス（ワイルドカードを正規表現にしたもの）。
# common.fetch の robots 判定は * を解釈しないため、念のためここでも確認する。
_DISALLOW = [r"/toushi/", r"/investmentBukkenList/", r".*/inquiry/", r".*/unit/", r"/pj/",
             r"/buy/draft/", r".*/callcenter/", r".*/commitment-id/"]


def _get(url: str) -> str:
    path = url[len(BASE):]
    if any(re.match(p, path) for p in _DISALLOW):
        raise Blocked(f"robots.txt で禁止: {url}")
    return fetch(url)


# ---------- Nuxt の devalue 形式 JSON を普通の dict/list に戻す ----------
_WRAPPERS = ("Reactive", "ShallowReactive", "Ref", "ShallowRef")


def _nuxt_data(html: str):
    m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise Blocked("__NUXT_DATA__ が見つかりません（ボット対策ページの可能性）")
    raw = json.loads(m.group(1))
    memo: dict[int, object] = {}

    def r(i):
        if not isinstance(i, int) or isinstance(i, bool) or i < 0:
            return None
        if i in memo:
            return memo[i]
        v = raw[i]
        if isinstance(v, list):
            if v and isinstance(v[0], str) and v[0] in _WRAPPERS:
                out = r(v[1])
            elif v and isinstance(v[0], str) and v[0] in ("Set", "Map", "Date", "Object", "BigInt", "RegExp",
                                                              "NuxtError", "EmptyRef", "EmptyShallowRef"):
                out = v[1] if v[0] == "Date" and len(v) > 1 else None
            else:
                out = []
                memo[i] = out
                out.extend(r(x) for x in v)
        elif isinstance(v, dict):
            out = {}
            memo[i] = out
            for k, x in v.items():
                out[k] = r(x)
        else:
            out = v
        memo[i] = out
        return out

    return r(0)


def _find(o, key):
    if isinstance(o, dict):
        if key in o:
            return o[key]
        o = list(o.values())
    if isinstance(o, list):
        for v in o:
            f = _find(v, key)
            if f is not None:
                return f
    return None


def _yen(man: float | None) -> str:
    if not man:
        return ""
    oku, rest = divmod(int(man), 10000)
    return (f"{oku}億" if oku else "") + (f"{rest:,}万円" if rest else "円" if oku else "")


def _kind(p: dict, labels: list[str]) -> str:
    t = p.get("propertyType") or ""
    if t == "tochi":
        return "土地"
    if any(re.search(r"アパート|マンション一棟|一棟|オーナーチェンジ|収益", x) for x in labels):
        return "収益・併用"
    if t.startswith("s_") or "新築戸建" in labels:
        return "新築戸建"
    return "中古戸建"


def _parse(html: str) -> tuple[list[Listing], int]:
    data = _nuxt_data(html)
    pag = _find(data, "propertyIndexPaginationProps") or {}
    pages = int(pag.get("lastPageNumber") or 1)
    out = []
    for pg in _find(data, "salePropertyPages") or []:
        for p in (pg or {}).get("saleProperties") or []:
            code = p.get("propertyCode")
            if not code:
                continue
            tags = p.get("tags") or {}
            labels = [norm(t.get("content", "")) for t in (tags.get("onImage") or []) + (tags.get("onDetail") or [])
                      if isinstance(t, dict)]
            infos = [norm(x) for x in (p.get("propertyInfos") or []) if isinstance(x, str)]
            address = infos[0] if infos else ""
            access = infos[1] if len(infos) > 1 else ""
            spec = infos[2] if len(infos) > 2 else ""
            kind = _kind(p, labels)
            price = p.get("price")
            price_man = float(price) if isinstance(price, (int, float)) and price > 0 else None
            if kind == "土地":
                land = parse_m2(spec.split("/")[0]) if spec else None
                bldg = None
            else:
                lm = re.search(r"土地\s*([\d.,]+\s*(?:㎡|m2))", spec)
                bm = re.search(r"建物\s*([\d.,]+\s*(?:㎡|m2))", spec)
                land = parse_m2(lm.group(1)) if lm else None
                bldg = parse_m2(bm.group(1)) if bm else None
            kp, yk = parse_ratio(spec)
            layout = spec.split("/")[0].strip() if kind != "土地" and spec else ""
            built = re.search(r"\d{4}年\d{1,2}月築(?:\(予定\))?", spec)
            out.append(Listing(
                site=NAME, id=code, kind=kind,
                title=norm(p.get("buildingName") or address),
                url=BASE + (p.get("propertyDetailPath") or f"/buy/{p.get('propertyType', 'kodate')}/bkdetail/{code}/"),
                price_text=_yen(price_man),
                price_man=price_man,
                address="東京都" + address if address and not address.startswith("東京都") else address,
                access=access, walk_min=parse_walk(access),
                land_m2=land, building_m2=bldg, kenpei=kp, yoseki=yk,
                extra=" ".join(x for x in [layout, built.group(0) if built else ""] + labels if x),
            ))
    return out, pages


def collect(log=print) -> list[Listing]:
    res = []
    for path, max_man in TYPES:
        for code, _, wname in config.WARDS:
            page, pages, n = 1, 1, 0
            while page <= min(pages, MAX_PAGES):
                url = f"{BASE}/buy/{path}/prefecture/13/city/{code}/?maxPrice={int(max_man)}"
                if page > 1:
                    url += f"&page={page}"
                items, pages = _parse(_get(url))
                res.extend(i for i in items if i.price_man is None or i.price_man <= max_man)
                n += len(items)
                page += 1
            log(f"  リハウス {path} {wname}: {n}件")
    return res
