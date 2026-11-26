"""三菱UFJ不動産販売 すまいーだ（23区をまとめて指定した検索一覧・価格上限は URL で指定）

robots.txt は全許可。1ページ30件。
- 土地 / 一戸建て: /buyers/{tochi|kodate}/tod_13/shik_000/?address_cd[]=13101…&price_to=
  （一戸建ての新築/中古は一覧の「新築」タグで判定）
- 投資用（23区 = tod_131）: 一棟マンション・一棟アパート・一棟ビル・投資用一戸建て・店舗付住宅
全件で 15〜20 リクエスト程度。
"""
import math
import re

from bs4 import BeautifulSoup

from .. import config
from ..common import Listing, fetch, norm, parse_m2, parse_price_man, parse_ratio, parse_walk, ward_of

NAME = "三菱UFJ不動産販売"
BASE = "https://www.sumai1.com"
PER_PAGE = 30
_PRICE_STEPS = [300, 500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000, 6000, 7000, 8000,
                9000, 10000, 12000, 15000, 20000]
# 投資用の物件種別（bukshu_N）: 区分マンション(1)・店舗事務所(7)・その他(99)は対象外
INVEST_TYPES = [(2, "一棟マンション"), (3, "一棟アパート"), (4, "一棟ビル"),
                (5, "投資用一戸建て"), (8, "店舗付住宅")]


def _price_to(limit: float) -> int:
    for v in _PRICE_STEPS:
        if v >= limit:
            return v
    return _PRICE_STEPS[-1]


def _home_url(path: str, limit: float, page: int) -> str:
    q = "&".join(f"address_cd[]={c}" for c, _, _ in config.WARDS) + f"&price_to={_price_to(limit)}"
    return f"{BASE}/buyers/{path}/tod_13/shik_000/" + (f"page/{page}" if page > 1 else "") + "?" + q


def _invest_url(no: int, limit: float, page: int) -> str:
    return (f"{BASE}/buyers/investor/tod_131/bukshu_{no}/" + (f"page/{page}" if page > 1 else "")
            + f"?price_to={_price_to(limit)}")


def _parse(html: str, mode: str, limit: float, type_label: str = "") -> tuple[list[Listing], int]:
    """mode: 'tochi' / 'kodate' / 'investor'"""
    soup = BeautifulSoup(html, "lxml")
    total = 0
    for st in soup.find_all("strong"):
        nxt = st.next_sibling
        if nxt and isinstance(nxt, str) and nxt.strip().startswith("件"):
            total = int(re.sub(r"\D", "", st.get_text()) or 0)
            break
    out = []
    for li in soup.select("li[id^=buk_]"):
        art = li.select_one("article")
        h = li.select_one("h2 a[href]")
        if not art or not h:
            continue
        m = re.search(r"/bukken/buk_([A-Za-z0-9]+)/", h["href"])
        if not m:
            continue
        f = {}
        for th in art.select("th"):
            k = norm(th.get_text())
            td = th.find_next_sibling("td")
            if k and td is not None and k not in f:   # PC用・SP用で同じ表が2回出るので最初だけ
                if k == "交通":
                    f[k] = " / ".join(norm(x.get_text()) for x in td.select(".block-data")) or norm(td.get_text(" "))
                else:
                    f[k] = norm(td.get_text(" "))
        address = f.get("所在地", "")
        if not ward_of(address):
            continue
        price_text = f.get("価格", "").replace(" ", "")
        price = parse_price_man(price_text)
        if price is not None and price > limit:
            continue
        labels = [norm(x.get_text()) for x in art.select(".category .label")]
        opts = [norm(x.get_text()) for x in art.select(".options li")]
        if mode == "tochi":
            kind = "土地"
        elif mode == "kodate":
            kind = "新築戸建" if "新築" in opts else "中古戸建"
        else:
            kind = "収益・併用"
        kp, yk = parse_ratio(next((v for k, v in f.items() if "建ぺい" in k or "容積" in k), ""))
        sent = art.select_one(".sentence")
        title = norm(h.get_text())
        extra = [type_label] + labels + opts + [f.get("間取り", ""), f.get("築年月", ""), f.get("構造", "")]
        if f.get("利回り"):
            extra.append("利回り" + f["利回り"].replace(" ", ""))
        extra.append(norm(sent.get_text(" ")) if sent else "")
        out.append(Listing(
            site=NAME, id=m.group(1), kind=kind, title=title,
            url=BASE + h["href"].split("?")[0],
            price_text=price_text, price_man=price,
            address=address, access=f.get("交通", ""), walk_min=parse_walk(f.get("交通", "")),
            land_m2=parse_m2(f.get("土地面積", "")), building_m2=parse_m2(f.get("建物面積", "")),
            kenpei=kp, yoseki=yk,
            extra=" ".join(x for x in extra if x)[:400],
        ))
    return out, total


def _crawl(url_of, mode: str, limit: float, label: str, type_label: str, log) -> list[Listing]:
    res, page, pages, total = [], 1, 1, 0
    while page <= pages:
        items, total = _parse(fetch(url_of(page)), mode, limit, type_label)
        pages = max(1, math.ceil(total / PER_PAGE))
        res.extend(items)
        page += 1
    log(f"  {NAME} {label} 23区: {total}件（{pages}ページ）")
    return res


def collect(log=print) -> list[Listing]:
    res = []
    res += _crawl(lambda p: _home_url("tochi", config.LAND_MAX_MAN, p), "tochi",
                  config.LAND_MAX_MAN, "土地", "", log)
    res += _crawl(lambda p: _home_url("kodate", config.TOTAL_MAX_MAN, p), "kodate",
                  config.TOTAL_MAX_MAN, "一戸建て", "", log)
    for no, label in INVEST_TYPES:
        res += _crawl(lambda p, no=no: _invest_url(no, config.TOTAL_MAX_MAN, p), "investor",
                      config.TOTAL_MAX_MAN, label, label, log)
    return res
