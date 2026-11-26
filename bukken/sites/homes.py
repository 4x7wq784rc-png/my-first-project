"""LIFULL HOME'S（区ごとの一覧ページ。robots.txt で禁止の /kksearch, /*from_dsp= 等は使わない）

URL: /{種別}/tokyo/{区}-city/list/?cond[sortby]=fee[&page=N]
  種別: tochi / kodate/shinchiku / kodate/chuko。1ページ30件。
  価格上限の指定（cond[moneyroomh]）は選択肢の値しか受け付けず（それ以外は 422）、
  土地は上限が「1億円」までしか選べない。そのため価格の安い順に並べ、
  ページ内の全物件が上限を超えたら打ち切る（上限超えは手元で除外）。
"""
import math
import re

from bs4 import BeautifulSoup

from .. import config
from ..common import (Blocked, Listing, fetch, norm, parse_m2, parse_price_man,
                      parse_ratio, parse_walk)

NAME = "LIFULL HOME'S"
# 無効化の理由: HOME'S はボット対策を導入しており、最初の1ページは取れても、続くリクエスト
# （3秒間隔でも）には HTTP 202・本文なし（ブラウザで JavaScript を実行させる確認ページ）が返る。
# 回避（ブラウザ実行・cookie の作り直し等）はしない方針のため、23区を取りきれない。
# 取得処理は実装済み（空ページを検知したらそこで打ち切り、それまでの物件を返す）。
ENABLED = False

BASE = "https://www.homes.co.jp"
PER_PAGE = 30
MAX_PAGES = 60
TYPES = [  # (URLの種別, 種類, 価格上限)
    ("tochi", "土地", config.LAND_MAX_MAN),
    ("kodate/shinchiku", "新築戸建", config.TOTAL_MAX_MAN),
    ("kodate/chuko", "中古戸建", config.TOTAL_MAX_MAN),
]


def _lines(td) -> list[str]:
    """<br> 区切りのセルを行のリストにする"""
    for br in td.find_all("br"):
        br.replace_with("\n")
    return [norm(x) for x in td.get_text().split("\n") if norm(x)]


def _split_access_address(lines: list[str]) -> tuple[str, str]:
    addr = [x for x in lines if re.match(r"^(東京都|.{1,4}区)", x) and "駅" not in x]
    acc = [x for x in lines if x not in addr]
    return " / ".join(acc), (addr[-1] if addr else "")


def _walk(access: str) -> int | None:
    # 「徒歩3～4分」→「徒歩3分」。バス便の行（「バス乗車6分「…」 徒歩3分」）は parse_walk が除外
    return parse_walk(re.sub(r"(\d+)\s*[～~〜-]\s*\d+\s*分", r"\1分", access))


def _total(soup) -> int:
    t = soup.select_one(".totalNum")
    return int(re.sub(r"\D", "", t.get_text()) or 0) if t else 0


def _id(href: str) -> str | None:
    m = re.search(r"/b-(\d+)/", href or "")
    return m.group(1) if m else None


def _make(kind, bid, title, f: dict, building_text: str, tags: list[str], comment: str) -> Listing:
    price = f.get("価格", "")
    access, address = _split_access_address(f.get("_交通所在地", []))
    kp, yk = parse_ratio(f.get("建ぺい率/容積率") or f.get("建ぺい率・容積率") or "")
    extra = " ".join(x for x in [
        title, f.get("間取り", ""), f.get("築年月", ""), f.get("階建/階", ""),
        f.get("建築条件", "") and "建築条件" + f.get("建築条件", ""),
        f.get("現況", ""), f.get("用途地域", ""), building_text, *tags, comment[:200],
    ] if x)
    return Listing(
        site=NAME, id=bid, kind=kind, title=title or address,
        url=f"{BASE}/{'tochi' if kind == '土地' else 'kodate'}/b-{bid}/",
        price_text=price, price_man=parse_price_man(price),
        address=address, access=access, walk_min=_walk(access),
        land_m2=parse_m2(f.get("土地面積", "")), building_m2=parse_m2(f.get("建物面積", "")),
        kenpei=kp, yoseki=yk, extra=extra,
    )


def _parse(html: str, kind: str) -> tuple[list[Listing], int]:
    if len(html.strip()) < 500:
        raise Blocked("HOME'S: 空のページ（ボット対策の確認ページ）が返されました")
    soup = BeautifulSoup(html, "lxml")
    out: list[Listing] = []
    for u in soup.select("div.mod-mergeBuilding--sale"):
        a = u.select_one("a.prg-bukkenNameAnchor")
        name = u.select_one(".bukkenName")
        title = norm(name.get_text()) if name else ""
        # 物件（建物）共通の表
        common: dict = {}
        tbl = u.select_one("table.verticalTable")
        if tbl:
            for tr in tbl.select("tr"):
                cells = tr.find_all(["th", "td"], recursive=False)
                for th, td in zip(cells[::2], cells[1::2]):
                    key = norm(th.get_text()).replace(" ", "")
                    if key in ("交通所在地",):
                        common["_交通所在地"] = _lines(td)
                    else:
                        common[key] = norm(td.get_text(" "))
        points = " ".join(norm(li.get_text()) for li in u.select(".bukkenPoint li"))
        rows = u.select("table.unitSummary tr.raSpecRow")
        if not rows:  # 1物件1件の形
            bid = _id(a["href"] if a else "")
            if not bid:
                continue
            tags = [norm(x.get_text()) for x in u.select(".relatedKeywordsData li")]
            out.append(_make(kind, bid, title, common, "", tags, points))
            continue
        # 建物の下に複数の住戸（区画）が並ぶ形
        heads = [norm(th.get_text()) for th in u.select("table.unitSummary thead th")]
        for tr in rows:
            bid = _id(tr.get("data-href", "")) or _id((tr.select_one("td.detail a") or {}).get("href", ""))
            if not bid:
                continue
            f = dict(common)
            for h, td in zip(heads, tr.find_all("td", recursive=False)):
                if h and h not in f:
                    f[h] = norm(td.get_text(" "))
            f["価格"] = f.get("価格", "").replace(" ", "")
            tags, comment = [], points
            sib = tr.find_next_sibling("tr")
            while sib is not None and "raSpecRow" not in (sib.get("class") or []):
                tags += [norm(x.get_text()) for x in sib.select(".relatedKeywordsData li")]
                c = sib.select_one(".textFeatureComment")
                if c:
                    comment = norm(c.get_text()) + " " + comment
                sib = sib.find_next_sibling("tr")
            out.append(_make(kind, bid, title, f, "", tags, comment))
    return out, _total(soup)


def _url(path: str, slug: str, page: int) -> str:
    return (f"{BASE}/{path}/tokyo/{slug}-city/list/?cond%5Bsortby%5D=fee"
            + (f"&page={page}" if page > 1 else ""))


def collect(log=print) -> list[Listing]:
    res: list[Listing] = []
    seen: set[str] = set()
    try:
        for path, kind, maxman in TYPES:
            for _, slug, wname in config.WARDS:
                page, pages, total = 1, 1, 0
                while page <= pages:
                    items, total = _parse(fetch(_url(path, slug, page)), kind)
                    pages = min(MAX_PAGES, max(1, math.ceil(total / PER_PAGE)))
                    for x in items:
                        if x.id in seen or (x.price_man is not None and x.price_man > maxman):
                            continue
                        seen.add(x.id)
                        res.append(x)
                    prices = [x.price_man for x in items if x.price_man is not None]
                    if not items or (prices and min(prices) > maxman):
                        break  # 価格の安い順なので、以降はすべて上限超え
                    page += 1
                log(f"  HOME'S {kind} {wname}: {total}件")
    except Blocked as e:
        log(f"  HOME'S: 取得を中断しました（{e}）。ここまでの {len(res)} 件を返します")
    return res
