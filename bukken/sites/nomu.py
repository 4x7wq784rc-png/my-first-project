"""野村の仲介 ノムコム（23区をまとめて指定した検索一覧。価格上限は URL で指定）

robots.txt で禁止されているのは eki_Search/・fpc= 付きURL などで、/{種別}/SearchList/ は許可。
1ページ40件。全件で 40〜50 リクエスト程度。
"""
import math
import re

from bs4 import BeautifulSoup

from .. import config
from ..common import Listing, fetch, norm, parse_m2, parse_price_man, parse_ratio, parse_walk, ward_of

NAME = "ノムコム"
BASE = "https://www.nomu.com"
TYPES = [  # (URLの種別, 種類, 価格上限)
    ("land", "土地", config.LAND_MAX_MAN),
    ("house_n", "新築戸建", config.TOTAL_MAX_MAN),
    ("house", "中古戸建", config.TOTAL_MAX_MAN),
]
PER_PAGE = 40
# 検索フォームの price_to に存在する値（これ以外は無視される可能性があるため、上限以上で最小の値を使う）
_PRICE_STEPS = [500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000, 5500, 6000, 7000,
                8000, 9000, 10000, 12000, 15000, 20000, 25000, 30000]


def _price_to(limit: float) -> int:
    for v in _PRICE_STEPS:
        if v >= limit:
            return v
    return _PRICE_STEPS[-1]


def _url(path: str, limit: float, page: int) -> str:
    wards = "".join(f"&area_id[]={code}" for code, _, _ in config.WARDS)
    u = f"{BASE}/{path}/SearchList/?type=area&wide=13{wards}&price_to={_price_to(limit)}"
    return u + (f"&pager_page={page}" if page > 1 else "")


def _ps(td) -> list[str]:
    return [norm(p.get_text(" ")) for p in td.find_all("p")] if td else []


def _parse(html: str, path: str, kind: str, limit: float) -> tuple[list[Listing], int]:
    soup = BeautifulSoup(html, "lxml")
    tot = soup.select_one(".item_total")
    total = int(re.sub(r"\D", "", tot.get_text()) or 0) if tot else 0
    out = []
    for u in soup.select("div.item_resultsmall"):
        a = u.select_one(".item_title a[href]")
        if not a:
            continue
        m = re.search(r"/id/([A-Za-z0-9]+)/", a["href"])
        if not m:
            continue
        loc = u.select_one(".item_location")
        address = norm(loc.get_text()) if loc else ""
        if not ward_of(address):
            continue
        acc = u.select_one(".item_access")
        access = norm(acc.get_text(" / ")) if acc else ""
        pr = u.select_one(".item_price")
        price_text = norm(pr.get_text("")) if pr else ""
        price = parse_price_man(price_text)
        if price is not None and price > limit:
            continue
        c4 = _ps(u.select_one("td.item_4"))
        c5 = _ps(u.select_one("td.item_5"))
        land = bldg = kp = yk = None
        extra = []
        if kind == "土地":   # 列: 土地面積 / 建ぺい率・容積率
            land = parse_m2(c4[0]) if c4 else None
            kp, yk = parse_ratio(" ".join(c5))
        else:                # 列: 建物面積・土地面積 / 築年月・間取り
            bldg = parse_m2(c4[0]) if len(c4) > 0 else None
            land = parse_m2(c4[1]) if len(c4) > 1 else None
            extra += c5
        point = u.select_one(".item_point")
        tags = [norm(t.get_text()) for t in u.select(".item_label")]
        title = norm(a.get_text())
        out.append(Listing(
            site=NAME, id=m.group(1), kind=kind, title=title,
            url=f"{BASE}/{path}/id/{m.group(1)}/",
            price_text=price_text, price_man=price,
            address=address, access=access, walk_min=parse_walk(access),
            land_m2=land, building_m2=bldg, kenpei=kp, yoseki=yk,
            extra=" ".join([title] + extra + [norm(point.get_text(" ")) if point else ""] + tags)[:400],
        ))
    return out, total


def collect(log=print) -> list[Listing]:
    res = []
    for path, kind, limit in TYPES:
        page, pages, total = 1, 1, 0
        while page <= pages:
            items, total = _parse(fetch(_url(path, limit, page)), path, kind, limit)
            pages = max(1, math.ceil(total / PER_PAGE))
            res.extend(items)
            page += 1
        log(f"  {NAME} {kind} 23区: {total}件（{pages}ページ）")
    return res
