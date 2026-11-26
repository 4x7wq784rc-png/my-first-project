"""at home（区ごとの一覧ページ。robots.txt は User-agent * に制限なし）

一覧ページはサーバー側で描画され、物件データが <script id="serverApp-state"> の JSON に
入っているので、それを読む。
URL: /{種別}/tokyo/{区}-city/list/[pageN/]?pref=13&cities={区}&basic={条件}&q=1&limit=100
  basic: kp001=価格下限なし, kp127=上限1億2000万, kp119=上限2億,
         kb206=新築一戸建て, kb208=中古一戸建て（価格未定 kp299 は含めない）
"""
import json
import math
import re

from bs4 import BeautifulSoup

from .. import config
from ..common import (Blocked, Listing, fetch, norm, parse_m2, parse_price_man,
                      parse_ratio, parse_walk)

NAME = "at home"
# 無効化の理由: at home はボット対策（JavaScript で cookie を発行させる「【アットホーム】認証中」
# ページ）を導入しており、数リクエスト（3秒間隔でも 5〜6 ページ目）で一覧の代わりにその
# 認証ページが返される。ブラウザ実行などで回避することはしない方針のため、毎日 23区×3種別
# （約200ページ）を取りきれない。取得処理自体は動く（認証ページを検知したらそこで打ち切り、
# それまでの物件を返す）ので、試すときは True にする。
ENABLED = False
BASE = "https://www.athome.co.jp"
PER_PAGE = 100
MAX_PAGES = 40  # 念のための上限（1区・1種別あたり）

# at home の価格上限コード（万円 → コード）
_PRICE_TO = {
    5000: "kp110", 6000: "kp112", 7000: "kp114", 8000: "kp115", 9000: "kp116",
    10000: "kp117", 11000: "kp126", 12000: "kp127", 13000: "kp128", 14000: "kp129",
    15000: "kp118", 16000: "kp130", 17000: "kp131", 18000: "kp132", 19000: "kp133",
    20000: "kp119",
}


def _price_code(max_man: int) -> str:
    """上限以上で最も小さいコード（ちょうどがなければ広めに取り、後で価格で絞る）"""
    for v in sorted(_PRICE_TO):
        if v >= max_man:
            return _PRICE_TO[v]
    return "kp120"  # 上限なし


TYPES = [  # (URLの種別パス, 追加の basic 条件, 種類, 価格上限)
    ("tochi", "", "土地", config.LAND_MAX_MAN),
    ("kodate/shinchiku", "kb206", "新築戸建", config.TOTAL_MAX_MAN),
    ("kodate/chuko", "kb208", "中古戸建", config.TOTAL_MAX_MAN),
]


def _state(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("script", id="serverApp-state")
    if not tag:
        t = soup.title.get_text() if soup.title else ""
        if "認証中" in t or "onProtectionInitialized" in html:
            raise Blocked("at home: ボット対策の認証ページ（JavaScript 必須）が返されました")
        raise Blocked("at home: 一覧データが見つかりません（ページ構成の変更か、拒否ページ）")
    return json.loads(tag.string or tag.get_text())


def _bukken_data(state: dict) -> dict | None:
    for key, v in state.items():
        if "bukken/list" not in key or not isinstance(v, dict) or "body" not in v:
            continue
        try:
            data = json.loads(v["body"]).get("data") or {}
        except (ValueError, AttributeError):
            continue
        bd = data.get("bukkenData") if isinstance(data, dict) else None
        if isinstance(bd, dict) and "bukkenList" in bd:
            return bd
    return None


def _price_text(k) -> str:
    if isinstance(k, str):  # 流通物件: "2,480" / "1億2,480"（単位は万円）
        t = norm(k)
        if not t or t in ("-", "－"):
            return ""
        return t if ("万" in t or "円" in t) else t + "万円"
    parts = []
    for p in (k or {}).get("priceText") or []:  # 新築分譲（入稿）物件
        oku, man = (p.get("priceOku") or "").strip(), (p.get("priceMan") or "").strip()
        s = (f"{oku}億" if oku and oku != "0" else "") + (f"{man}万" if man and man != "0" else "")
        if s:
            parts.append(s + (p.get("unitText") or "円"))
    txt = ((k or {}).get("bufferText") or "～").join(parts) if parts else ""
    return norm(txt or (k or {}).get("otherUnitText") or (k or {}).get("noPlan") or "")


def _clean(s) -> str:
    s = norm(str(s or ""))
    return "" if s in ("-", "－", "null", "None") or s.startswith("null") else s


def _to_listing(b: dict, kind: str) -> Listing | None:
    """一覧の1件。新築分譲（isNyuko）と流通物件でJSONの形が違うので両方読む"""
    no = str(b.get("bukkenNo") or "")
    if not no:
        return None
    nyuko = bool(b.get("isNyuko"))
    seo = b.get("seoRoma") or ("tochi" if kind == "土地" else "kodate")
    price_text = _price_text(b.get("kakaku"))
    if nyuko:
        acc = [a.get("accessText") for a in b.get("access") or []]
        land, bldg = b.get("landareaFromTo"), b.get("buildingFromTo")
        bcr = b.get("buildingCoverageRatio")
        syumoku = (b.get("propertyDetailData") or {}).get("syumoku") or ""
        built = _clean(b.get("buildComplete"))
        built = f"完成{built}" if built else ""
        right = b.get("right")
        notes = [norm(" ".join(p for p in (b.get("pointData") or {}).get("points") or [] if isinstance(p, str)))[:200]]
    else:
        acc = [a.get("name") for a in b.get("bukkenAccess") or []]
        land, bldg = b.get("tochiMs"), (b.get("areaInfo") or {}).get("area")
        bcr = b.get("buildingToLandRatio")
        syumoku = b.get("syumokuNm") or ""
        info = b.get("bukkenInfo") or {}
        built = " ".join(x for x in (_clean(info.get("chikunengetsu")),
                                    _clean(info.get("construction"))) if x)
        right = b.get("tochiKenriNm")
        notes = [_clean(b.get("saitekiYoto")),
                 _clean(b.get("rimawari")) and "利回り" + _clean(b.get("rimawari")),
                 norm((b.get("osusumeComment") or {}).get("comment") or "")[:200]]
    access = " / ".join(norm(a) for a in acc if a and norm(a))
    # 「徒歩3～4分」→「徒歩3分」として最短分数を読む
    walk = parse_walk(re.sub(r"(\d+)\s*[～~〜-]\s*\d+\s*分", r"\1分", access))
    loc = _clean(b.get("location")).replace(" ", "")
    if loc and not loc.startswith("東京都"):
        loc = "東京都" + loc
    kp, yk = parse_ratio(f"建ぺい率{_clean(bcr)} 容積率{_clean(b.get('floorAreaRatio'))}")
    title = _clean(b.get("title"))
    extra = " ".join(x for x in [title, syumoku, _clean(b.get("madori")), _clean(b.get("kaidateKai")),
                                 built, _clean(right), *notes] if x)
    return Listing(
        site=NAME, id=no, kind=kind,
        title=title or loc,
        url=f"{BASE}/{seo}/{no}/",
        price_text=price_text, price_man=parse_price_man(price_text),
        address=loc, access=access, walk_min=walk,
        land_m2=parse_m2(_clean(land)), building_m2=parse_m2(_clean(bldg)),
        kenpei=kp, yoseki=yk, extra=extra,
    )


def _parse(html: str, kind: str) -> tuple[list[Listing], int]:
    bd = _bukken_data(_state(html))
    if bd is None:
        raise Blocked("at home: 物件一覧の JSON が見つかりません")
    out = []
    for b in bd.get("bukkenList") or []:
        try:
            x = _to_listing(b, kind)
        except (TypeError, ValueError, AttributeError):  # 1件の形がおかしくても他は読む
            continue
        if x:
            out.append(x)
    return out, int(bd.get("bukkenCount") or 0)


def _url(path: str, slug: str, basic: str, page: int) -> str:
    pg = f"page{page}/" if page > 1 else ""
    return (f"{BASE}/{path}/tokyo/{slug}-city/list/{pg}"
            f"?pref=13&cities={slug}&basic={basic}&q=1&limit={PER_PAGE}")


def collect(log=print) -> list[Listing]:
    res: list[Listing] = []
    seen: set[str] = set()
    try:
        for path, kb, kind, maxman in TYPES:
            basic = ",".join(x for x in (kb, "kp001", _price_code(maxman)) if x)
            for _, slug, wname in config.WARDS:
                page, pages, total = 1, 1, 0
                while page <= pages:
                    items, total = _parse(fetch(_url(path, slug, basic, page)), kind)
                    pages = min(MAX_PAGES, max(1, math.ceil(total / PER_PAGE)))
                    for x in items:
                        if x.id in seen:
                            continue
                        if x.price_man is not None and x.price_man > maxman:
                            continue
                        seen.add(x.id)
                        res.append(x)
                    if not items:
                        break
                    page += 1
                log(f"  at home {kind} {wname}: {total}件")
    except Blocked as e:
        log(f"  at home: 取得を中断しました（{e}）。ここまでの {len(res)} 件を返します")
    return res
