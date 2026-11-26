"""オウチーノ（o-uccino.com）— 東京都版トップの「人気物件ランキング」だけを取得する限定版

制限（2026-11 確認）:
  - 区別・条件別の検索一覧（/front/tochi/pref_13/city_13114/ や /front/search/?a=...&e=l）は
    サーバー側では空のHTMLを返し、物件はブラウザ上で JavaScript が https://search.o-uccino.jp の
    API から読み込む。この実行環境では search.o-uccino.jp と assets.o-uccino.jp（JS 本体）への
    接続がプロキシに拒否されるため、検索一覧は取得できない（サイト側のブロックではない）。
  - 都道府県トップ（/front/{tochi|kodate/shinchiku|kodate/chuko}/pref_13/）だけは
    サーバー側でランキング上位10件が描画されるので、それを読み、23区・予算内のものだけ残す。
    1回あたり3リクエスト。取れる件数は各種別最大10件（都下を含むため23区内はさらに少ない）。
  - robots.txt: /front/favorites, /front/recently, /beta, 一部の /front/estates/ID は禁止。
    詳細ページは取得しない（一覧のURLを記録するだけ）。fetch() が robots.txt を確認する。
  環境で search.o-uccino.jp を許可すれば、API の robots.txt を確認したうえで全件取得に拡張できる可能性あり。
"""
import re

from bs4 import BeautifulSoup

from .. import config
from ..common import Listing, fetch, norm, parse_m2, parse_price_man, parse_ratio, parse_walk, ward_of

NAME = "オウチーノ"
BASE = "https://o-uccino.com"
TYPES = [  # (パス, 種類, 価格上限)
    ("tochi", "土地", config.LAND_MAX_MAN),
    ("kodate/shinchiku", "新築戸建", config.TOTAL_MAX_MAN),
    ("kodate/chuko", "中古戸建", config.TOTAL_MAX_MAN),
]


def _parse(html: str, kind: str, limit: float) -> tuple[list[Listing], int]:
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], 0
    for card in soup.select("div[class*=CardItem__card___]"):
        a = card.select_one("[class*=CardItem__name] a[href]") or card.select_one('a[href*="/front/estates/"]')
        if not a:
            continue
        m = re.search(r"/front/estates/([A-Za-z0-9]+)/", a["href"])
        if not m:
            continue
        seen += 1
        chips = [norm(x.get_text()) for x in card.select("[class*=EstateChips] span")]
        price_el = card.select_one("[class*=CardItem__price]")
        price_text = norm(price_el.get_text()) if price_el else ""
        texts = [norm(x.get_text(" ")) for x in card.select("[class*=CardItem__trafficText]")]
        spec_el = card.select_one("[class*=CardItem__spec]")
        spec = norm(spec_el.get_text(" ")) if spec_el else ""
        address = next((t for t in texts if ward_of(t) or re.search(r"[区市町村]", t) and "駅" not in t), "")
        access = " / ".join(t for t in texts if t != address)
        if not ward_of(address):
            continue
        price = parse_price_man(price_text)
        if price is not None and price > limit:
            continue
        parts = [p.strip() for p in spec.split("|")]
        land = bld = None
        layout = []
        for p in parts:
            if p.startswith("土地"):
                land = parse_m2(p)
            elif p.startswith("建物"):
                bld = parse_m2(p)
            elif "建ぺい" in p or "容積" in p:
                pass
            elif re.search(r"㎡|m2", p) and kind == "土地" and land is None:
                land = parse_m2(p)
            elif p:
                layout.append(p)
        kp, yk = parse_ratio(spec)
        # 新築/中古は URL で分けているが、カードのバッジでも確認する
        k = kind
        if kind != "土地":
            if "新築" in chips:
                k = "新築戸建"
            elif "中古" in chips:
                k = "中古戸建"
        title = norm(a.get_text())
        out.append(Listing(
            site=NAME, id=m.group(1), kind=k, title=title,
            url=BASE + a["href"].split("?")[0],
            price_text=price_text, price_man=price,
            address=address, access=access, walk_min=parse_walk(access),
            land_m2=land, building_m2=bld, kenpei=kp, yoseki=yk,
            extra=" ".join(x for x in [title] + chips + layout if x)[:400],
        ))
    return out, seen


def collect(log=print) -> list[Listing]:
    res, ids = [], set()
    for path, kind, limit in TYPES:
        items, seen = _parse(fetch(f"{BASE}/front/{path}/pref_13/"), kind, limit)
        items = [x for x in items if x.id not in ids]
        ids.update(x.id for x in items)
        res.extend(items)
        log(f"  {NAME} {kind} 東京都ランキング: {seen}件中 23区・予算内 {len(items)}件（検索一覧は取得不可）")
    return res
