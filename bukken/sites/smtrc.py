"""三井住友トラスト不動産（23区をまとめて指定した検索一覧）

robots.txt は特定のボット以外は全許可。一覧URLの priceto は価格上限の「番号」
（1000,1500,…,10000,20000,30000 万円の何番目か）で、20000万円 = 15。
1ページ30件。土地・戸建（新築/中古は一覧のアイコン表記で判定）で全件 10〜15 リクエスト程度。
"""
import math
import re

from bs4 import BeautifulSoup

from .. import config
from ..common import Listing, fetch, norm, parse_m2, parse_price_man, parse_walk, ward_of

NAME = "三井住友トラスト不動産"
BASE = "https://smtrc.jp"
PER_PAGE = 30
# サイトの価格上限の選択肢（priceto はこのリストの 1 始まりの番号）
_PRICE_STEPS = [1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000, 6000, 7000, 8000, 9000,
                10000, 20000, 30000]
TYPES = [  # (bukenkind, 種類(土地以外は一覧の表記で判定), 価格上限)
    (3, "土地", config.LAND_MAX_MAN),
    (2, "戸建", config.TOTAL_MAX_MAN),
]


def _priceto(limit: float) -> int | None:
    for i, v in enumerate(_PRICE_STEPS, 1):
        if v >= limit:
            return i
    return None


def _url(kind_no: int, limit: float, page: int) -> str:
    codes = ",".join(c for c, _, _ in config.WARDS)
    pt = _priceto(limit)
    u = f"{BASE}/list/listViewLive/index?search=city&prefcode=13&bukenkind={kind_no}&citycode={codes}"
    if pt:
        u += f"&priceto={pt}"
    return u + (f"&pageno={page}" if page > 1 else "")


def _parse(html: str, base_kind: str, limit: float) -> tuple[list[Listing], int]:
    soup = BeautifulSoup(html, "lxml")
    kk = soup.select_one(".kekka span")
    total = int(re.sub(r"\D", "", kk.get_text()) or 0) if kk else 0
    out = []
    for b in soup.select("div.block_list"):
        a = b.select_one(".property_name_btns a[href*=propertyCode]")
        if not a:
            continue
        m = re.search(r"propertyCode=([A-Za-z0-9]+)", a["href"])
        if not m:
            continue
        address = norm(a.get_text())
        if not ward_of(address):
            continue
        icon = norm(b.select_one(".bukken_icon").get_text()) if b.select_one(".bukken_icon") else ""
        if base_kind == "土地":
            kind = "土地"
        elif "新築" in icon:
            kind = "新築戸建"
        elif "中古" in icon:
            kind = "中古戸建"
        else:
            continue
        f = {}
        for su in b.select(".spec_unit"):
            ut, ud = su.select_one(".ut"), su.select_one(".ud")
            if ut and ud:
                k = norm(ut.get_text())
                f[k] = norm(ud.get_text(" / " if k == "交通" else ""))
        price_text = f.get("価格", "")
        price = parse_price_man(price_text)
        if price is not None and price > limit:
            continue
        land = bldg = None
        if kind == "土地":
            land = parse_m2(f.get("土地面積", ""))
        else:
            men = f.get("面積", "")
            mb = re.search(r"([\d.,]+)\s*m2?\s*\(建物\)", men)
            ml = re.search(r"([\d.,]+)\s*m2?\s*\(土地\)", men)
            bldg = float(mb.group(1).replace(",", "")) if mb else None
            land = float(ml.group(1).replace(",", "")) if ml else None
        text = b.select_one(".text")
        tags = [i.get("alt", "") for i in b.select(".icons img")]
        access = f.get("交通", "")
        out.append(Listing(
            site=NAME, id=m.group(1), kind=kind, title=f"{address} {icon}".strip(),
            url=f"{BASE}/detail/CompareDetails?propertyCode={m.group(1)}",
            price_text=price_text, price_man=price,
            address=address, access=access, walk_min=parse_walk(access),
            land_m2=land, building_m2=bldg,
            extra=" ".join([icon, f.get("間取り", ""), f.get("築年月", ""), f.get("現況", "")] + tags
                           + [norm(text.get_text(" ")) if text else ""])[:400],
        ))
    return out, total


def collect(log=print) -> list[Listing]:
    res = []
    for kind_no, base_kind, limit in TYPES:
        page, pages, total = 1, 1, 0
        while page <= pages:
            items, total = _parse(fetch(_url(kind_no, limit, page)), base_kind, limit)
            pages = max(1, math.ceil(total / PER_PAGE))
            res.extend(items)
            page += 1
        log(f"  {NAME} {base_kind} 23区: {total}件（{pages}ページ）")
    return res
