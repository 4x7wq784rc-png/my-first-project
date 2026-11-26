"""Yahoo!不動産（区ごとの一覧ページ）

robots.txt（User-agent: *）では検索系の
  /land/search/?…  /used/house/search/?…  /new/house/search/?…（?cid= 以外）
  …/search/*?start=  …/search/*&start=  …/search/*?*[*]=  …/search/*?*?
などが禁止されている。一方、区ごとのパス形式
  /land/search/03/13/<区コード>/?p_to=<円>&page=<n>
はどの Disallow にも当たらないので、これだけを使う（ページ送りは page=、start= は使わない）。
common.fetch の robots 判定（urllib.robotparser）は * ワイルドカードを解釈しないため、
ここでワイルドカード対応の判定も追加で行う。
"""
import json
import re

from bs4 import BeautifulSoup

from .. import config
from ..common import Blocked, Listing, fetch, norm, parse_m2, parse_price_man, parse_walk

NAME = "Yahoo!不動産"
BASE = "https://realestate.yahoo.co.jp"
TYPES = [  # (URLの種別, 種類, 価格上限 万円)
    ("land", "土地", config.LAND_MAX_MAN),
    ("new/house", "新築戸建", config.TOTAL_MAX_MAN),
    ("used/house", "中古戸建", config.TOTAL_MAX_MAN),
]
MAX_PAGES = 30  # 念のための上限（1ページ30件）


# ---------- robots.txt（ワイルドカード対応）----------
_rules: list[tuple[bool, re.Pattern, int]] | None = None


def _load_rules() -> list[tuple[bool, re.Pattern, int]]:
    rules, active, in_ua = [], False, False
    for line in fetch(BASE + "/robots.txt", check_robots=False).splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        k, v = (x.strip() for x in line.split(":", 1))
        k = k.lower()
        if k == "user-agent":
            if not in_ua:
                active = False
            in_ua = True
            active = active or v == "*"
            continue
        in_ua = False
        if active and k in ("allow", "disallow") and v:
            pat = re.escape(v).replace(r"\*", ".*")
            if pat.endswith(r"\$"):
                pat = pat[:-2] + "$"
            rules.append((k == "allow", re.compile(pat), len(v)))
    return rules


def _robots_ok(url: str) -> bool:
    global _rules
    if _rules is None:
        _rules = _load_rules()
    path = url[len(BASE):] if url.startswith(BASE) else url
    best = None  # (長さ, allow)
    for allow, pat, n in _rules:
        if pat.match(path) and (best is None or n > best[0] or (n == best[0] and allow)):
            best = (n, allow)
    return best is None or best[1]


def _get(url: str) -> str:
    if not _robots_ok(url):
        raise Blocked(f"robots.txt で禁止: {url}")
    return fetch(url)


# ---------- 解析 ----------
def _context(html: str) -> dict:
    m = re.search(r"window\.__SERVER_SIDE_CONTEXT__\s*=\s*(\{.*?\});\s*/\*\]\]>", html, re.S)
    if not m:
        raise Blocked("一覧データが見つかりません（ページ構成変更または拒否）")
    return json.loads(m.group(1))


def _parse(html: str, kind: str) -> tuple[list[Listing], int]:
    pages = int(_context(html).get("pagination", {}).get("totalPage") or 1)
    soup = BeautifulSoup(html, "lxml")
    out = []
    for it in soup.select("li._listItem"):
        a = it.select_one('a[data-testid="link:cassette-title"]')
        if not a:
            continue  # 広告枠など
        url = a["href"].split("#")[0].split("?")[0]
        m = re.search(r"/detail[^/]*/([^/]+)/", url)
        if not m:
            continue
        h2 = it.select_one(".ListCassette2__ttl__txt")
        title = norm(h2.get_text(" ")) if h2 else norm(a.get_text(" "))
        tags = [norm(t.get_text()) for t in it.select(".ListCassette2__pointUnit--ttl li")]
        tags += [norm(t.get_text()) for t in it.select("li._listCassette .ListCassette2__info__cnt li")]
        tags = [t for t in tags if t and not re.search(r"もらえる|写真あり|TOP10", t)]
        price_el = it.select_one(".ListCassette2__info__price")
        price_text = re.sub(r"(価格更新|値下げ|NEW)$", "", norm(price_el.get_text(" ")) if price_el else "").strip()
        access = address = area = built = layout = ""
        for li in it.select(".ListCassette2--header .ListCassette2__info__dtl"):
            t = norm(li.get_text(" "))
            if re.search(r"「.+」駅|バス|徒歩", t) and not access:
                access = t
            elif "東京都" in t and not address:
                address = t
            elif re.search(r"土地|建物", t) and re.search(r"m\s*2|㎡", t):
                area = t
            elif "築" in t:
                built = t
            else:
                layout = t
        land = re.search(r"土地\s*([\d.,]+\s*m\s*2)", area)
        bldg = re.search(r"建物\s*([\d.,]+\s*m\s*2)", area)
        # 新築戸建の一覧に建築条件付き土地（URLが /land/）が混ざるので URL で種類を決める
        k = "土地" if "/land/" in url else "中古戸建" if "/used/house/" in url else \
            "新築戸建" if "/new/house/" in url else kind
        out.append(Listing(
            site=NAME, id=m.group(1), kind=k, title=title, url=url,
            price_text=price_text, price_man=parse_price_man(price_text),
            address=address, access=access, walk_min=parse_walk(access),
            land_m2=parse_m2(land.group(1)) if land else None,
            building_m2=parse_m2(bldg.group(1)) if bldg else None,
            extra=" ".join(x for x in [layout, built] + list(dict.fromkeys(tags)) if x),
        ))
    return out, pages


def collect(log=print) -> list[Listing]:
    res, seen = [], set()
    caps = {"土地": config.LAND_MAX_MAN}
    for path, kind, max_man in TYPES:
        for code, _, wname in config.WARDS:
            page, pages, n = 1, 1, 0
            while page <= min(pages, MAX_PAGES):
                url = f"{BASE}/{path}/search/03/13/{code}/?p_to={int(max_man) * 10000}"
                if page > 1:
                    url += f"&page={page}"
                items, pages = _parse(_get(url), kind)
                for i in items:
                    # 念のため手元でも価格で絞る（価格未定は残す）。重複（種別をまたぐ掲載）は除く
                    cap = caps.get(i.kind, config.TOTAL_MAX_MAN)
                    if i.id not in seen and (i.price_man is None or i.price_man <= cap):
                        seen.add(i.id)
                        res.append(i)
                n += len(items)
                page += 1
            log(f"  Yahoo {kind} {wname}: {n}件")
    return res
