"""共通部品：取得（間隔を空ける・robots.txt 確認）と、文字から数値を読む処理"""
import re
import time
import unicodedata
from dataclasses import dataclass, field, asdict
from urllib.parse import urlparse

import requests

from . import config

_session = requests.Session()
_session.headers.update({"User-Agent": config.USER_AGENT, "Accept-Language": "ja,en;q=0.8"})
_last_hit: dict[str, float] = {}
_robots: dict[str, list] = {}


class Blocked(Exception):
    """サイト側に拒否された（403/429 など）"""


def _parse_robots(text: str) -> list[tuple[bool, str]]:
    """User-agent: * のグループの (許可か, パターン) を返す"""
    rules, agents, in_rules = [], [], False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        k, v = (x.strip() for x in line.split(":", 1))
        k = k.lower()
        if k == "user-agent":
            if in_rules:
                agents, in_rules = [], False
            agents.append(v)
        elif k in ("allow", "disallow"):
            in_rules = True
            if "*" in agents and v:
                rules.append((k == "allow", v))
    return rules


def _match(pattern: str, path: str) -> bool:
    rx = re.escape(pattern).replace(r"\*", ".*")
    if rx.endswith(r"\$"):
        rx = rx[:-2] + "$"
    return re.match(rx, path) is not None


def allowed_by_robots(url: str) -> bool:
    """Google 方式（* と $ に対応、最も長く一致した規則を採用、同じ長さなら許可）"""
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    rules = _robots.get(base)
    if rules is None:
        try:
            r = _session.get(base + "/robots.txt", timeout=20)
            rules = _parse_robots(r.text) if r.status_code == 200 else []
        except requests.RequestException:
            rules = []
        _robots[base] = rules
    path = p.path + (("?" + p.query) if p.query else "")
    best = None
    for allow, pat in rules:
        if _match(pat, path):
            if best is None or len(pat) > len(best[1]) or (len(pat) == len(best[1]) and allow):
                best = (allow, pat)
    return best is None or best[0]


def fetch(url: str, *, encoding: str | None = None, check_robots: bool = True) -> str:
    if check_robots and not allowed_by_robots(url):
        raise Blocked(f"robots.txt で禁止: {url}")
    host = urlparse(url).netloc
    wait = config.REQUEST_INTERVAL_SEC - (time.time() - _last_hit.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    for attempt in range(3):
        _last_hit[host] = time.time()
        try:
            r = _session.get(url, timeout=40)
        except requests.RequestException as e:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code in (403, 429, 503):
            if attempt == 2 or r.status_code == 403:
                raise Blocked(f"HTTP {r.status_code}: {url}")
            time.sleep(15 * (attempt + 1))
            continue
        r.raise_for_status()
        if encoding:
            r.encoding = encoding
        elif r.encoding is None or r.encoding.lower() == "iso-8859-1":
            r.encoding = r.apparent_encoding
        return r.text
    raise Blocked(url)


# ---------- 物件データ ----------
KINDS = ("土地", "新築戸建", "中古戸建", "収益・併用")


@dataclass
class Listing:
    site: str            # サイト名（例: SUUMO）
    id: str              # サイト内で一意のID
    kind: str            # KINDS のどれか
    title: str
    url: str
    price_text: str = ""
    price_man: float | None = None     # 万円（幅がある場合は下限）
    address: str = ""
    access: str = ""
    walk_min: int | None = None        # 最寄駅徒歩（分）。バス便は None
    land_m2: float | None = None
    building_m2: float | None = None
    kenpei: float | None = None        # 建ぺい率 %
    yoseki: float | None = None        # 容積率 %
    extra: str = ""                    # 判定に使う追加テキスト（間取り・特徴など）
    # 判定結果（run.py が設定）
    rank: str = ""
    reasons: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.site}:{self.id}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["key"] = self.key
        return d


# ---------- 文字から数値を読む ----------
def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"\s+", " ", s).strip()


def parse_price_man(s: str) -> float | None:
    """'8489万円～1億247万円' → 8489, '1億2000万円' → 12000"""
    s = norm(s).replace(",", "")
    for m in re.finditer(r"(?:(\d+(?:\.\d+)?)億)?\s*(?:(\d+(?:\.\d+)?)万)?円?", s):
        oku, man = m.group(1), m.group(2)
        if oku or man:
            return float(oku or 0) * 10000 + float(man or 0)
    return None


def parse_m2(s: str) -> float | None:
    """'106.84m2（32.31坪）' → 106.84（幅がある場合は下限）"""
    s = re.sub(r"m\s*2", "m2", norm(s).replace(",", ""))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:m2|m²|㎡|平米|m\b)", s)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*坪", s)
    if m:
        return round(float(m.group(1)) * 3.30579, 2)
    return None


def parse_walk(s: str) -> int | None:
    """アクセス文から最短の徒歩分数。バス便のみなら None"""
    s = norm(s)
    best = None
    for part in re.split(r"[/、,・\n]|\s{2,}", s) or [s]:
        if "バス" in part:
            continue
        m = re.search(r"(?:徒歩|歩)\s*(\d+)\s*分", part)
        if m:
            v = int(m.group(1))
            best = v if best is None else min(best, v)
    return best


def parse_ratio(s: str) -> tuple[float | None, float | None]:
    """'建ぺい率60%、容積率200%' や '60％・200％' → (60, 200)"""
    s = norm(s)
    kp = re.search(r"建[ぺペ蔽]い?率[^\d]{0,6}(\d+(?:\.\d+)?)", s)
    yk = re.search(r"容積率[^\d]{0,6}(\d+(?:\.\d+)?)", s)
    if kp or yk:
        return (float(kp.group(1)) if kp else None, float(yk.group(1)) if yk else None)
    nums = re.findall(r"(\d+(?:\.\d+)?)\s*%", s)
    if len(nums) >= 2:
        return float(nums[0]), float(nums[1])
    return None, None


def ward_of(address: str) -> str:
    a = norm(address)
    for name in config.WARD_NAMES:
        if name in a:
            return name
    return ""
