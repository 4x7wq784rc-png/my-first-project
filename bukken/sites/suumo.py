"""SUUMO（区ごとの一覧ページ。robots.txt で許可された静的URLのみ使用）"""
import math
import re

from bs4 import BeautifulSoup

from .. import config
from ..common import Listing, fetch, norm, parse_m2, parse_price_man, parse_ratio, parse_walk

NAME = "SUUMO"
BASE = "https://suumo.jp"
# SUUMO の価格上限は 1億2000万円 までしか指定できないため、それを超える場合は上限なし(9999999)で取得し後で絞る
TYPES = [  # (URLの種別, 種類, 価格上限)
    ("tochi", "土地", config.LAND_MAX_MAN),
    ("ikkodate", "新築戸建", config.TOTAL_MAX_MAN if config.TOTAL_MAX_MAN <= 12000 else 9999999),
    ("chukoikkodate", "中古戸建", config.TOTAL_MAX_MAN if config.TOTAL_MAX_MAN <= 12000 else 9999999),
]


def _parse(html: str, kind: str) -> tuple[list[Listing], int]:
    soup = BeautifulSoup(html, "lxml")
    hit = soup.select_one(".pagination_set-hit")
    total = int(re.sub(r"\D", "", hit.get_text()) or 0) if hit else 0
    out = []
    for u in soup.select("div.property_unit"):
        a = u.select_one(".property_unit-title a")
        if not a:
            continue
        href = a["href"]
        m = re.search(r"nc_(\d+)", href)
        if not m:
            continue
        f = {}
        for dl in u.select("dl"):
            dt, dd = dl.find("dt"), dl.find("dd")
            if dt and dd:
                f[norm(dt.get_text())] = norm(dd.get_text(" "))
        tags = [norm(t.get_text()) for t in u.select(".property_unit-pcts li")]
        kp, yk = parse_ratio(f.get("建ぺい率・容積率", ""))
        out.append(Listing(
            site=NAME, id=m.group(1), kind=kind,
            title=f.get("物件名") or norm(a.get_text()),
            url=BASE + href.split("?")[0],
            price_text=f.get("販売価格", ""), price_man=parse_price_man(f.get("販売価格", "")),
            address=f.get("所在地", ""), access=f.get("沿線・駅", ""),
            walk_min=parse_walk(f.get("沿線・駅", "")),
            land_m2=parse_m2(f.get("土地面積", "")), building_m2=parse_m2(f.get("建物面積", "")),
            kenpei=kp, yoseki=yk,
            extra=" ".join([norm(a.get_text()), f.get("間取り", ""), f.get("築年月", "")] + tags),
        ))
    return out, total


def collect(log=print) -> list[Listing]:
    res = []
    for path, kind, kt in TYPES:
        for _, slug, wname in config.WARDS:
            page, pages = 1, 1
            while page <= pages:
                url = f"{BASE}/{path}/tokyo/sc_{slug}/?kt={kt}&pc=100" + (f"&page={page}" if page > 1 else "")
                items, total = _parse(fetch(url), kind)
                pages = max(1, math.ceil(total / 100))
                res.extend(items)
                page += 1
            log(f"  SUUMO {kind} {wname}: {total}件")
    return res
