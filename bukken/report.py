"""一覧ページ（HTML）を作る。データはページ内に埋め込み、絞り込み・並べ替えはブラウザ側で行う。"""
import datetime as dt
import json
import re
from pathlib import Path

from . import config
from .common import norm, ward_of


HEIYO_WORDS = ("賃貸併用", "併用住宅", "オーナー住戸", "賃貸付", "貸室", "アパート併用")


def built_year(text: str) -> int | None:
    """説明文から建築年を読む（'2019年3月築' '2019年築' '築7年' '2019年3月' の順に探す）"""
    t = norm(text)
    m = re.search(r"(19[5-9]\d|20[0-4]\d)年\s*\d{1,2}月\s*築", t) or re.search(r"(19[5-9]\d|20[0-4]\d)年築", t)
    if m:
        return int(m.group(1))
    m = re.search(r"築\s*(\d{1,2})年", t)
    if m:
        return dt.date.today().year - int(m.group(1))
    m = re.search(r"(19[5-9]\d|20[0-4]\d)年\s*\d{1,2}月", t)
    return int(m.group(1)) if m else None


def _group(rows: list[dict]) -> list[dict]:
    """同じ物件が複数サイトに出ている場合、1件にまとめてリンクを並べる"""
    groups: dict[tuple, dict] = {}
    for r in rows:
        ward = ward_of(r["address"]) or ward_of(r["title"])
        size = r["land_m2"] if r["kind"] == "土地" else r["building_m2"]
        if r["price_man"] and size:
            k = (r["kind"], ward, round(r["price_man"]), round(size))
        else:
            k = (r["key"],)
        g = groups.get(k)
        link = {"site": r["site"], "url": r["url"]}
        text = r["title"] + " " + r.get("extra", "")
        built = built_year(text) if r["kind"] != "土地" else None
        heiyo = r["kind"] != "土地" and any(w in norm(text) for w in HEIYO_WORDS)
        if g is None:
            g = dict(r, ward=ward, links=[link], built=built, heiyo=heiyo)
            groups[k] = g
        else:
            if all(x["site"] != r["site"] for x in g["links"]):
                g["links"].append(link)
            g["first_seen"] = min(g["first_seen"], r["first_seen"])
            g["heiyo"] = g["heiyo"] or heiyo
            if built and (not g.get("built") or built < g["built"]):
                g["built"] = built
            for f in ("kenpei", "yoseki", "walk_min", "land_m2", "building_m2"):
                if g.get(f) is None and r.get(f) is not None:
                    g[f] = r[f]
            if r["rank"] < g["rank"]:
                g["rank"], g["reasons"] = r["rank"], r["reasons"]
    out = []
    for g in groups.values():
        out.append({k: g.get(k) for k in (
            "kind", "rank", "title", "price_text", "price_man", "price_change", "address", "ward", "access",
            "walk_min", "land_m2", "building_m2", "kenpei", "yoseki", "reasons", "first_seen", "links", "built", "heiyo")})
    return out


def write_report(path: Path, today: str, first_run: bool, status: list[dict], rows: list[dict]) -> None:
    items = _group(rows)
    payload = {
        "date": today, "firstRun": first_run, "status": status, "items": items,
        "cond": {
            "landMax": config.LAND_MAX_MAN, "totalMax": config.TOTAL_MAX_MAN,
            "floorTarget": config.FLOOR_TARGET_M2, "walkMax": config.WALK_MAX_MIN,
        },
        "wards": config.WARD_NAMES,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    (path.parent / "items.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    path.write_text(TEMPLATE, encoding="utf-8")


TEMPLATE = r"""<meta charset="utf-8">
<title>23区 賃貸併用ウォッチ</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Zen+Kaku+Gothic+New:wght@500;700&family=Noto+Sans+JP:wght@400;500;700&family=IBM+Plex+Mono:wght@500&display=swap">
<style>
/* 地番図のような「区画」の一覧。上に今日の要約、下に絞り込みと物件カード */
:root{
  --bg:#f4f6f8; --surface:#ffffff; --line:#dde2e8; --fg:#18202c; --muted:#5d6878;
  --accent:#2c4f7c; --accent-soft:#e3eaf4; --new:#17795a; --new-soft:#e0f2ea;
  --warn:#a35a12; --warn-soft:#f8ecdd; --down:#17795a; --up:#b4402f;
  --f-display:"Zen Kaku Gothic New","Hiragino Sans","Noto Sans JP",sans-serif;
  --f-body:"Noto Sans JP","Hiragino Sans","Yu Gothic",sans-serif;
  --f-num:"IBM Plex Mono",ui-monospace,"SFMono-Regular",monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#10151d; --surface:#171e29; --line:#2a3443; --fg:#e6ebf2; --muted:#98a3b3;
  --accent:#8fb2e3; --accent-soft:#1f2d42; --new:#5fcf9f; --new-soft:#15302a;
  --warn:#e3a35e; --warn-soft:#33261a; --down:#5fcf9f; --up:#ef8a78; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#10151d; --surface:#171e29; --line:#2a3443; --fg:#e6ebf2; --muted:#98a3b3;
  --accent:#8fb2e3; --accent-soft:#1f2d42; --new:#5fcf9f; --new-soft:#15302a;
  --warn:#e3a35e; --warn-soft:#33261a; --down:#5fcf9f; --up:#ef8a78; color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font-family:var(--f-body);font-size:15px;line-height:1.6;
  padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:24px 48px}
.wrap{max-width:1080px;margin:0 auto;display:flex;flex-direction:column;gap:20px}
h1{font-family:var(--f-display);font-weight:700;font-size:1.6rem;margin:0;text-wrap:balance}
h2{font-family:var(--f-display);font-weight:700;font-size:1.1rem;margin:0}
.sub{color:var(--muted);font-size:.85rem}
.num{font-family:var(--f-num);font-variant-numeric:tabular-nums}
header{display:flex;flex-direction:column;gap:4px}
.summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:12px 14px;display:flex;flex-direction:column;gap:2px}
.tile b{font-family:var(--f-num);font-size:1.6rem;font-weight:500}
.tile.new b{color:var(--new)}
.note{background:var(--accent-soft);border-radius:8px;padding:10px 14px;font-size:.88rem}
details.sites{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:10px 14px;font-size:.88rem}
details.sites summary{cursor:pointer;font-weight:500}
.sitegrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:6px 16px;margin-top:10px}
.sitegrid span.bad{color:var(--warn)}
.filters{display:flex;flex-wrap:wrap;gap:8px;align-items:center;position:sticky;top:env(safe-area-inset-top,0px);
  background:var(--bg);padding-block:8px;z-index:5;border-bottom:1px solid var(--line)}
body::before{content:"";position:fixed;inset:0 0 auto;height:env(safe-area-inset-top,0px);z-index:10;background:var(--bg)}
.chip{font:inherit;font-size:.85rem;border:1px solid var(--line);background:var(--surface);color:var(--fg);
  border-radius:999px;padding:4px 12px;cursor:pointer}
.chip[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:var(--surface)}
.chip:focus-visible,select:focus-visible,a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
select{font:inherit;font-size:.85rem;border:1px solid var(--line);background:var(--surface);color:var(--fg);border-radius:6px;padding:4px 8px}
.count{margin-left:auto;color:var(--muted);font-size:.85rem}
.list{display:flex;flex-direction:column;gap:10px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:14px 16px;
  display:grid;grid-template-columns:auto 1fr auto;gap:4px 14px;align-items:start}
.card.is-new{border-color:var(--new)}
.rank{font-family:var(--f-display);font-weight:700;width:2.2rem;height:2.2rem;border-radius:6px;display:grid;place-items:center;grid-row:span 3}
.rank.A{background:var(--accent);color:var(--surface)}
.rank.B{border:1.5px solid var(--accent);color:var(--accent)}
.head{display:flex;flex-wrap:wrap;gap:6px;align-items:center;min-width:0}
.title{font-weight:700;min-width:0;overflow-wrap:anywhere}
.tag{font-size:.75rem;border-radius:4px;padding:1px 6px;background:var(--accent-soft);color:var(--accent);white-space:nowrap}
.tag.new{background:var(--new-soft);color:var(--new)}
.tag.warn{background:var(--warn-soft);color:var(--warn)}
.price{text-align:right;grid-row:span 2}
.price b{font-family:var(--f-num);font-size:1.25rem;font-weight:500;white-space:nowrap}
.price .chg.down{color:var(--down)} .price .chg.up{color:var(--up)}
.facts{grid-column:2;display:flex;flex-wrap:wrap;gap:2px 16px;color:var(--muted);font-size:.86rem;min-width:0}
.facts span{overflow-wrap:anywhere}
.why{font-size:.86rem;grid-column:2 / 4;min-width:0}
.links{grid-column:2 / 4;display:flex;flex-wrap:wrap;gap:8px}
.links a{font-size:.85rem;color:var(--accent);text-decoration:none;border:1px solid var(--line);border-radius:6px;padding:2px 10px}
.links a:hover{background:var(--accent-soft)}
.empty{text-align:center;color:var(--muted);padding:40px 0}
@media (max-width:560px){
  .card{grid-template-columns:auto 1fr;gap:8px 12px}
  .rank{grid-row:span 1}
  .price,.facts,.why,.links{grid-column:1 / -1;grid-row:auto;text-align:left}
}
</style>

<div class="wrap">
  <header>
    <h1>23区 賃貸併用ウォッチ</h1>
    <div class="sub" id="cond"></div>
  </header>
  <section class="summary" id="summary"></section>
  <div class="note" id="note" hidden></div>
  <details class="sites"><summary id="siteSum"></summary><div class="sitegrid" id="sites"></div></details>
  <nav class="filters" aria-label="絞り込み">
    <button class="chip" id="fNew" aria-pressed="true">新着のみ</button>
    <button class="chip" id="fHeiyo" aria-pressed="false">築20年以内の賃貸併用</button>
    <button class="chip" data-kind="土地" aria-pressed="false">土地</button>
    <button class="chip" data-kind="新築戸建" aria-pressed="false">新築</button>
    <button class="chip" data-kind="中古戸建" aria-pressed="false">中古</button>
    <button class="chip" data-kind="収益・併用" aria-pressed="false">収益・併用</button>
    <button class="chip" id="fA" aria-pressed="false">A判定のみ</button>
    <select id="fWard" aria-label="区"><option value="">全23区</option></select>
    <select id="fSort" aria-label="並べ替え">
      <option value="rank">判定順</option><option value="new">新着順</option>
      <option value="built">築年が新しい順</option><option value="price">価格が安い順</option><option value="walk">駅に近い順</option>
    </select>
    <span class="count" id="count"></span>
  </nav>
  <section class="list" id="list"></section>
</div>

<script>
let D;
const $ = s => document.querySelector(s);
const yen = m => m == null ? "-" : (m >= 10000 ? (Math.floor(m/10000) + "億" + (m%10000 ? Math.round(m%10000).toLocaleString() + "万" : "")) : Math.round(m).toLocaleString() + "万") + "円";
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const isNew = it => it.first_seen === D.date;

fetch("items.json").then(r => r.json()).then(d => { D = d; start(); }).catch(() => { document.querySelector("#list").innerHTML = '<p class="empty">データを読み込めませんでした。ページを再読み込みしてください。</p>'; });
function start() {
$("#cond").textContent = `${D.date} 更新 ・ 土地 ${yen(D.cond.landMax)}以下／新築・中古 ${yen(D.cond.totalMax)}以下 ・ 駅徒歩${D.cond.walkMax}分以内`;
const nNew = D.items.filter(isNew).length;
const byKind = k => D.items.filter(i => i.kind === k && isNew(i)).length;
$("#summary").innerHTML = [
  ["new", "今日の新着", nNew],
  ["", "新着の土地", byKind("土地")],
  ["", "新着の建物付き", byKind("新築戸建") + byKind("中古戸建") + byKind("収益・併用")],
  ["", "掲載中の候補", D.items.length],
].map(([c, l, v]) => `<div class="tile ${c}"><span class="sub">${l}</span><b>${v}</b></div>`).join("");
if (D.firstRun) { const n = $("#note"); n.hidden = false;
  n.textContent = "初回の取得のため、いま掲載中の候補をすべて「新着」として表示しています。明日からは前日になかった物件だけが新着になります。"; }
const ok = D.status.filter(s => s.ok).length;
$("#siteSum").textContent = `取得したサイト ${ok} / ${D.status.length}`;
$("#sites").innerHTML = D.status.map(s => s.ok
  ? `<span>${esc(s.site)}：<span class="num">${s.fetched}</span>件中 候補<span class="num">${s.candidates}</span></span>`
  : `<span class="bad">${esc(s.site)}：取得できず（${esc(s.error)}）</span>`).join("");
for (const w of D.wards) $("#fWard").insertAdjacentHTML("beforeend", `<option>${w}</option>`);

const st = { onlyNew: nNew > 0, heiyo20: false, kinds: new Set(), onlyA: false, ward: "", sort: "rank" };
const thisYear = Number(D.date.slice(0, 4));
const isHeiyo20 = it => it.heiyo && it.built && it.built >= thisYear - 20;
try { const s = JSON.parse(localStorage.getItem("filters") || "null"); if (s) { st.kinds = new Set(s.kinds); st.onlyA = s.onlyA; st.ward = s.ward; st.sort = s.sort; } } catch (e) {}

function card(it) {
  const tags = [];
  if (isNew(it)) tags.push(`<span class="tag new">新着</span>`);
  tags.push(`<span class="tag">${esc(it.kind)}</span>`);
  if ((it.reasons || []).some(r => r.includes("建築条件"))) tags.push(`<span class="tag warn">建築条件</span>`);
  const chg = it.price_change ? `<div class="chg ${it.price_change < 0 ? "down" : "up"} num">${it.price_change < 0 ? "値下げ " : "値上げ "}${yen(Math.abs(it.price_change))}</div>` : "";
  const tsubo = it.kind === "土地" && it.price_man && it.land_m2 ? `<div class="sub num">坪 ${Math.round(it.price_man / (it.land_m2 / 3.30579)).toLocaleString()}万円</div>` : "";
  const f = [];
  if (it.address) f.push(esc(it.address));
  if (it.access) f.push(esc(it.access));
  if (it.land_m2) f.push(`土地 <span class="num">${it.land_m2}</span>㎡`);
  if (it.building_m2) f.push(`建物 <span class="num">${it.building_m2}</span>㎡`);
  if (it.built) f.push(`<span class="num">${it.built}</span>年築（築<span class="num">${thisYear - it.built}</span>年）`);
  if (it.kenpei || it.yoseki) f.push(`建ぺい/容積 <span class="num">${it.kenpei ?? "-"}/${it.yoseki ?? "-"}</span>%`);
  return `<article class="card ${isNew(it) ? "is-new" : ""}">
    <div class="rank ${it.rank}" title="${it.rank === "A" ? "有力" : "検討"}">${it.rank}</div>
    <div class="head">${tags.join("")}<span class="title">${esc(it.title)}</span></div>
    <div class="price"><b>${esc(it.price_text || yen(it.price_man))}</b>${tsubo}${chg}</div>
    <div class="facts">${f.map(x => `<span>${x}</span>`).join("")}</div>
    <div class="why">${esc((it.reasons || []).join(" ／ "))}<span class="sub"> ・ 初掲載 ${esc(it.first_seen)}</span></div>
    <div class="links">${it.links.map(l => `<a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.site)}で見る</a>`).join("")}</div>
  </article>`;
}
function render() {
  document.querySelectorAll("[data-kind]").forEach(b => b.setAttribute("aria-pressed", st.kinds.has(b.dataset.kind)));
  $("#fNew").setAttribute("aria-pressed", st.onlyNew); $("#fHeiyo").setAttribute("aria-pressed", st.heiyo20); $("#fA").setAttribute("aria-pressed", st.onlyA);
  $("#fWard").value = st.ward; $("#fSort").value = st.sort;
  let xs = D.items.filter(i => (!st.onlyNew || isNew(i)) && (!st.heiyo20 || isHeiyo20(i)) && (!st.kinds.size || st.kinds.has(i.kind))
    && (!st.onlyA || i.rank === "A") && (!st.ward || i.ward === st.ward));
  const big = 1e9, cmp = {
    rank: (a, b) => a.rank.localeCompare(b.rank) || (b.first_seen.localeCompare(a.first_seen)) || ((a.walk_min ?? big) - (b.walk_min ?? big)),
    new: (a, b) => b.first_seen.localeCompare(a.first_seen) || a.rank.localeCompare(b.rank),
    price: (a, b) => (a.price_man ?? big) - (b.price_man ?? big),
    built: (a, b) => (b.built ?? 0) - (a.built ?? 0) || ((a.walk_min ?? big) - (b.walk_min ?? big)),
    walk: (a, b) => (a.walk_min ?? big) - (b.walk_min ?? big),
  }[st.sort];
  xs.sort(cmp);
  $("#count").textContent = `${xs.length}件`;
  const shown = xs.slice(0, 300);
  $("#list").innerHTML = shown.length ? shown.map(card).join("") + (xs.length > 300 ? `<p class="empty">ほか${xs.length - 300}件。区や種類で絞り込んでください。</p>` : "")
    : `<p class="empty">条件に合う物件はありません。「新着のみ」などの絞り込みを外すと、掲載中の候補をすべて表示します。</p>`;
  try { localStorage.setItem("filters", JSON.stringify({ kinds: [...st.kinds], onlyA: st.onlyA, ward: st.ward, sort: st.sort })); } catch (e) {}
}
document.querySelectorAll("[data-kind]").forEach(b => b.onclick = () => { st.kinds.has(b.dataset.kind) ? st.kinds.delete(b.dataset.kind) : st.kinds.add(b.dataset.kind); render(); });
$("#fNew").onclick = () => { st.onlyNew = !st.onlyNew; render(); };
// 押すと掲載中の全件から探す（新着のみは外す）。並びは新しい建物順
$("#fHeiyo").onclick = () => { st.heiyo20 = !st.heiyo20; if (st.heiyo20) { st.onlyNew = false; st.sort = "built"; } else if (st.sort === "built") st.sort = "rank"; render(); };
$("#fA").onclick = () => { st.onlyA = !st.onlyA; render(); };
$("#fWard").onchange = e => { st.ward = e.target.value; render(); };
$("#fSort").onchange = e => { st.sort = e.target.value; render(); };
render();
}
</script>
"""
