"""センチュリー21（23区をまとめて指定した一覧 /{種別}/tokyo/b_list?city[]=…）

robots.txt で禁止されているのは /api/* のみ。一覧は HTML に全項目が入っている（1ページ最大100件）。
price_to の選択肢は 1億円が上限なので、1億円超は送らず価格はこちらで絞り込む。
事業投資用（/biz/）はマンション・アパート・店舗付住宅・一戸建・ビルの「一棟」だけを残す。
全件で 15 リクエスト前後（1ページ 1.5MB 程度と重い）。
"""
import math
import re

from bs4 import BeautifulSoup

from .. import config
from ..common import Listing, fetch, norm, parse_m2, parse_price_man, parse_ratio, parse_walk, ward_of

NAME = "センチュリー21"
BASE = "https://www.century21.jp"
PER_PAGE = 100
TYPES = [  # (URLの種別, 種類, 価格上限, 追加パラメータ)
    ("tochi", "土地", config.LAND_MAX_MAN, ""),
    ("newkodate", "新築戸建", config.TOTAL_MAX_MAN, ""),
    ("usedkodate", "中古戸建", config.TOTAL_MAX_MAN, ""),
    # 41マンション 42アパート 43店舗付住宅 44一戸建 47ビル（区分は一覧で除外）
    ("biz", "収益・併用", config.TOTAL_MAX_MAN, "".join(f"&kinds[]={k}" for k in (41, 42, 43, 44, 47))),
]


def _url(path: str, limit: float, extra: str, page: int) -> str:
    q = "&".join(f"city[]={c}" for c, _, _ in config.WARDS)
    if limit <= 10000:   # サイトの選択肢は 1億円まで
        q += f"&price_to={int(limit)}"
    q += extra + f"&limit={PER_PAGE}"
    return f"{BASE}/{path}/tokyo/b_list?{q}" + (f"&page={page}" if page > 1 else "")


def _parse(html: str, kind: str, limit: float) -> tuple[list[Listing], int]:
    soup = BeautifulSoup(html, "lxml")
    total = 0
    for b in soup.find_all("b"):
        nxt = b.next_sibling
        if isinstance(nxt, str) and nxt.strip().startswith("件") and re.fullmatch(r"[\d,]+", b.get_text(strip=True)):
            total = int(b.get_text(strip=True).replace(",", ""))
            break
    out = []
    for a in soup.select("a.card--property-detail--name-link[href]"):
        m = re.search(r"/detail/([0-9A-Za-z-]+)", a["href"])
        if not m:
            continue
        card = a.parent   # カテゴリ表示を含むカード全体までさかのぼる
        while card is not None and not card.select_one(".card--property--cat--parent"):
            card = card.parent
        if card is None:
            continue
        child = card.select_one(".card--property--cat--child")
        child = norm(child.get_text()) if child else ""
        if kind == "収益・併用" and child == "区分":
            continue
        f = {}
        for dl in card.select("dl.card--property-detail--data"):
            dt, dd = dl.find("dt"), dl.find("dd")
            if dt and dd:
                k = norm(dt.get_text())
                if k == "最寄り駅":
                    f[k] = " / ".join(norm(BeautifulSoup(x, "lxml").get_text(" "))
                                      for x in re.split(r"<br\s*/?>", dd.decode_contents())
                                      if norm(BeautifulSoup(x, "lxml").get_text()))
                else:
                    f[k] = norm(dd.get_text(""))
        address = f.get("所在地", "")
        if not ward_of(address):
            continue
        pr = card.select_one(".card--property--price")
        price_text = norm(pr.get_text()) if pr else ""
        price = parse_price_man(price_text)
        if price is not None and price > limit:
            continue
        txt = card.select_one(".card--property-detail--txt")
        kp, yk = parse_ratio(next((v for k, v in f.items() if "建ぺい" in k or "容積" in k), ""))
        title = norm(a.get_text())
        extra = [child, f.get("間取り", ""), f.get("築年月", ""), f.get("建物現況", ""),
                 f.get("物件現況", ""), f.get("建築条件", "") and "建築条件" + f.get("建築条件", ""),
                 f.get("用途地域", "")]
        if f.get("利回り"):
            extra.append("利回り" + f["利回り"])
        extra.append(norm(txt.get_text(" ")) if txt else "")
        access = f.get("最寄り駅", "")
        out.append(Listing(
            site=NAME, id=m.group(1), kind=kind, title=title,
            url=a["href"] if a["href"].startswith("http") else BASE + a["href"],
            price_text=price_text, price_man=price,
            address=address, access=access, walk_min=parse_walk(access),
            land_m2=parse_m2(f.get("土地面積") or f.get("敷地面積") or ""),
            building_m2=parse_m2(f.get("建物面積") or f.get("延床面積") or ""),
            kenpei=kp, yoseki=yk,
            extra=" ".join(x for x in [title] + extra if x)[:400],
        ))
    return out, total


def collect(log=print) -> list[Listing]:
    res = []
    for path, kind, limit, extra in TYPES:
        page, pages, total = 1, 1, 0
        while page <= pages:
            items, total = _parse(fetch(_url(path, limit, extra, page)), kind, limit)
            pages = max(1, math.ceil(total / PER_PAGE))
            res.extend(items)
            page += 1
        log(f"  {NAME} {kind} 23区: {total}件（{pages}ページ）")
    return res
