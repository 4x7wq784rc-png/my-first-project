"""住友不動産販売 ステップ（区ごとの静的一覧ページ /{種別}/area_13/list_13_1xx/100_{page}/）

robots.txt で /search/list/ と /mapsearch/ は禁止のため、サイトマップにも載っている区別一覧だけを使う。
都の一覧ページ（/tochi/area_13/ など）に区ごとの件数が出るので、物件のある区だけを取得する。
区別一覧では価格の絞り込みができないので、価格はこちらで絞り込む。
新築一戸建ては /kodate/6/area_13/ 配下（物件のある区だけリンクがある）。
全件で 40〜50 リクエスト程度。
"""
import math
import re

from bs4 import BeautifulSoup

from .. import config
from ..common import Listing, fetch, norm, parse_m2, parse_price_man, parse_ratio, parse_walk, ward_of

NAME = "住友不動産販売"
BASE = "https://www.stepon.co.jp"
PER_PAGE = 100
ENC = "cp932"   # Shift_JIS 宣言だが機種依存文字（Ⅱ など）を含む
TYPES = [  # (一覧のパス, 既定の種類, 価格上限)
    ("tochi", "土地", config.LAND_MAX_MAN),
    ("kodate/6", "新築戸建", config.TOTAL_MAX_MAN),
    ("kodate", "中古戸建", config.TOTAL_MAX_MAN),
]
_WARD_CODES = {c[2:]: name for c, _, name in config.WARDS}   # "112" -> 世田谷区


def _ward_counts(path: str) -> list[tuple[str, int]]:
    """都の一覧ページから (区コード3桁, 件数) を得る（23区・件数>0のみ）"""
    soup = BeautifulSoup(fetch(f"{BASE}/{path}/area_13/", encoding=ENC), "lxml")
    res = []
    for a in soup.select("a[href]"):
        m = re.search(rf"/{re.escape(path)}/area_13/list_13_(\d{{3}})/$", a["href"])
        if not m or m.group(1) not in _WARD_CODES:
            continue
        cnt = a.select_one(".cs-selector__link-count")
        n = int(re.sub(r"\D", "", cnt.get_text()) or 0) if cnt else 1
        if n > 0 and m.group(1) not in [r[0] for r in res]:
            res.append((m.group(1), n))
    return res


def _parse(html: str, path: str, default_kind: str, limit: float) -> tuple[list[Listing], int]:
    soup = BeautifulSoup(html, "lxml")
    c = soup.select_one("#search-count-result")
    total = int(re.sub(r"\D", "", c.get_text()) or 0) if c else 0
    out = []
    for card in soup.select("div.sr-card"):
        a = card.select_one("a.sr-card__name[href]")
        if not a:
            continue
        m = re.search(r"/detail_([0-9A-Za-z]+)/", a["href"])
        if not m:
            continue
        labels = [norm(x.get_text()) for x in card.select(".sr-card__labels .label")]
        tlabel = norm(card.select_one("#type_label").get_text()) if card.select_one("#type_label") else ""
        if default_kind == "土地":
            kind = "土地"
        elif "新築" in tlabel:
            kind = "新築戸建"
        elif "中古" in tlabel:
            kind = "中古戸建"
        else:
            kind = default_kind
        pr = card.select_one(".sr-card__price")
        price_text = re.sub(r"\s+", "", pr.get_text("")) if pr else ""
        price = parse_price_man(price_text)
        if price is not None and price > limit:
            continue
        txt = card.select_one(".sr-card__text")
        address = ""
        if txt:
            first = None
            for s in txt.find_all(string=True, recursive=False):
                if norm(s):
                    first = s
                    break
            address = norm(first or "")
        if not ward_of(address):
            continue
        access = " / ".join(norm(p.get_text(" ")) for p in card.select("p[id^=railStation]") if norm(p.get_text()))
        spec = ""
        for p in (txt.find_all("p", recursive=False) if txt else []):
            if not (p.get("id") or "").startswith("railStation"):
                spec = norm(p.get_text(" "))
        tm = card.select_one("#label_tochiMenseki")
        bm = card.select_one("#label_tatemonoMenseki")
        land = float(re.sub(r"[^\d.]", "", tm.get_text()) or 0) or None if tm else None
        bldg = float(re.sub(r"[^\d.]", "", bm.get_text()) or 0) or None if bm else None
        kp, yk = parse_ratio(spec)
        title = norm(a.get_text())
        out.append(Listing(
            site=NAME, id=m.group(1), kind=kind, title=title,
            url=a["href"] if a["href"].startswith("http") else BASE + a["href"],
            price_text=price_text, price_man=price,
            address=address, access=access, walk_min=parse_walk(access),
            land_m2=land, building_m2=bldg, kenpei=kp, yoseki=yk,
            extra=" ".join(x for x in [title] + labels + [spec] if x)[:400],
        ))
    return out, total


def collect(log=print) -> list[Listing]:
    res, seen = [], set()
    for path, kind, limit in TYPES:
        n_all = 0
        for code, cnt in _ward_counts(path):
            pages = max(1, math.ceil(cnt / PER_PAGE))
            page = 1
            while page <= pages:
                html = fetch(f"{BASE}/{path}/area_13/list_13_{code}/{PER_PAGE}_{page}/", encoding=ENC)
                items, total = _parse(html, path, kind, limit)
                pages = max(1, math.ceil(total / PER_PAGE)) if total else pages
                for it in items:
                    if it.id not in seen:
                        seen.add(it.id)
                        res.append(it)
                page += 1
            n_all += cnt
        log(f"  {NAME} {kind} 23区: {n_all}件")
    return res
