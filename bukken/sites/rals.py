"""不動産投資連合隊（収益物件）https://www.rals.net/invest

（https://rengotai.rals.co.jp/ は加盟店向けの広告案内サイトで物件一覧は無い。物件検索は www.rals.net/invest）
robots.txt（www.rals.net）は一部の SEO ボットを禁止しているだけで、一般のクローラーは制限なし。
検索一覧はサーバー側で描画される（1ページ50件・?page=N）。
  /invest/search?a1=13&a2=<23区のコード,…>&div=<種別,…>&pmax=<円>&page=N
  種別(div): 46 一棟アパート / 47 一棟マンション / 50 一棟ビル / 68 賃貸併用住宅 / 54 店舗付住宅 / 49 一戸建て
  （48 区分マンション・52 区分店舗・53 区分事務所・57 倉庫工場・60 ホテル・51 駐車場・64 その他 は対象外）
  pmax は円単位。
一覧の下に「検索条件に近い物件」が混ざることがあるので、区・価格はモジュール側でも確認する。
全件で 6 リクエスト程度（2026-11 時点で 23区・2億以下 272件）。
"""
import math
import re

from bs4 import BeautifulSoup

from .. import config
from ..common import Listing, fetch, norm, parse_m2, parse_price_man, parse_walk, ward_of

NAME = "不動産投資連合隊"
BASE = "https://www.rals.net"
PER_PAGE = 50
DIVS = "46,47,50,68,54,49"
_EXCLUDE = ("区分",)


def _url(page: int) -> str:
    wards = ",".join(c for c, _, _ in config.WARDS)
    return (f"{BASE}/invest/search?a1=13&a2={wards}&div={DIVS}&pmax={int(config.TOTAL_MAX_MAN) * 10000}"
            + (f"&page={page}" if page > 1 else ""))


def _parse(html: str) -> tuple[list[Listing], int]:
    soup = BeautifulSoup(html, "lxml")
    body = soup.get_text("|", strip=True)
    m = re.search(r"該当物件：\|([\d,]+)\|件", body)
    total = int(m.group(1).replace(",", "")) if m else 0
    out = []
    for art in soup.select("article"):
        a = art.find("a", href=re.compile(r"^/invest/\d+"))
        h2 = art.find("h2")
        if not a or not h2:
            continue
        pid = re.match(r"/invest/(\d+)", a["href"]).group(1)
        badges = [norm(b.get_text()) for b in art.select("[data-slot=badge]")]
        badges = [b for b in badges if b and b != "NEW"]
        if any(x in b for b in badges for x in _EXCLUDE):
            continue
        price_text = ""
        for sp in art.find_all("span"):
            t = norm(sp.get_text(""))
            if re.fullmatch(r"[\d,億万]+円", t):
                price_text = t
                break
        price = parse_price_man(price_text)
        texts = [norm(p.get_text("")) for p in art.select("p[data-scope=text]")]
        address = next((t for t in texts if t.startswith("東京都") or ward_of(t)), "")
        if not ward_of(address):
            continue
        if price is not None and price > config.TOTAL_MAX_MAN:
            continue
        access = ""
        for p in art.select("p[data-scope=text]"):
            spans = p.select("span > span")
            if spans:
                access = " ".join(norm(s.get_text("")) for s in spans)
                break
        spans = [norm(s.get_text("")) for s in art.find_all("span")]
        land = bld = None
        yld = ""
        for i, t in enumerate(spans[:-1]):
            if t == "建物" and bld is None:
                bld = parse_m2(spans[i + 1])
            elif t == "土地" and land is None:
                land = parse_m2(spans[i + 1])
            elif t == "利回り" and not yld:
                yld = spans[i + 1]
        facts = [t for t in spans if re.fullmatch(r"(築\d+年|新築|\d+階建|全\d+戸|地下\d+階.*)", t)]
        title = norm(h2.get_text())
        extra = badges + facts + ([f"利回り{yld}"] if yld else []) + [title]
        out.append(Listing(
            site=NAME, id=pid, kind="収益・併用", title=title,
            url=f"{BASE}/invest/{pid}",
            price_text=price_text, price_man=price,
            address=address, access=access, walk_min=parse_walk(access),
            land_m2=land, building_m2=bld,
            extra=" ".join(dict.fromkeys(x for x in extra if x))[:400],
        ))
    return out, total


def collect(log=print) -> list[Listing]:
    res, seen, page, pages, total = [], set(), 1, 1, 0
    while page <= pages:
        items, total = _parse(fetch(_url(page)))
        pages = min(max(1, math.ceil(total / PER_PAGE)), 20)
        for x in items:
            if x.id not in seen:
                seen.add(x.id)
                res.append(x)
        page += 1
    log(f"  {NAME} 23区 一棟・併用・戸建等: {total}件（{pages}ページ）→ {len(res)}件")
    return res
