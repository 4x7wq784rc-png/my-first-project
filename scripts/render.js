#!/usr/bin/env node
// ROADMAP.md をスタイル付きの単一HTMLファイルにレンダリングする
const fs = require('fs');
const path = require('path');
const { marked } = require('marked');

const src = path.join(__dirname, '..', 'ROADMAP.md');
const out = path.join(__dirname, '..', 'roadmap.html');

const md = fs.readFileSync(src, 'utf8');

// GFM（テーブル・チェックボックス等）を有効化
marked.setOptions({ gfm: true, breaks: false });
const body = marked.parse(md);

const html = `<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>売上100億円企業をつくるためのロードマップ</title>
<style>
  :root { --fg:#1f2328; --muted:#656d76; --accent:#0969da; --border:#d0d7de; --bg:#ffffff; --code-bg:#f6f8fa; }
  * { box-sizing: border-box; }
  body { margin:0; background:#eef1f4; color:var(--fg);
    font-family: -apple-system, "Hiragino Sans", "Yu Gothic UI", "Segoe UI", Meiryo, sans-serif;
    line-height:1.7; }
  .wrap { max-width: 900px; margin: 0 auto; padding: 48px 24px 96px; }
  .card { background:var(--bg); border:1px solid var(--border); border-radius:12px;
    padding: 40px 48px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
  h1 { font-size: 2rem; border-bottom: 2px solid var(--border); padding-bottom:.4em; }
  h2 { font-size: 1.5rem; margin-top: 2.2em; border-bottom: 1px solid var(--border); padding-bottom:.3em; }
  h3 { font-size: 1.15rem; margin-top: 1.8em; color:#24292f; }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }
  blockquote { margin: 1em 0; padding: .4em 1em; color: var(--muted);
    border-left: 4px solid var(--accent); background: #f0f6ff; border-radius: 0 6px 6px 0; }
  code { background: var(--code-bg); padding: .15em .4em; border-radius: 6px;
    font-family: "SFMono-Regular", Consolas, monospace; font-size: .9em; }
  pre { background: var(--code-bg); padding: 16px; border-radius: 8px; overflow:auto;
    border: 1px solid var(--border); }
  pre code { background: none; padding: 0; }
  table { border-collapse: collapse; width: 100%; margin: 1em 0; font-size: .95em; }
  th, td { border: 1px solid var(--border); padding: 8px 12px; text-align: left; }
  th { background: var(--code-bg); }
  tr:nth-child(even) td { background: #fafbfc; }
  ul.contains-task-list { list-style: none; padding-left: .2em; }
  .task-list-item input { margin-right: .5em; }
  hr { border: none; border-top: 1px solid var(--border); margin: 2.5em 0; }
  .meta { color: var(--muted); font-size: .85rem; text-align:right; margin-top: 2em; }
</style>
</head>
<body>
  <div class="wrap">
    <article class="card">
${body}
    </article>
    <p class="meta">Generated from ROADMAP.md &middot; ${new Date().toISOString().slice(0,10)}</p>
  </div>
</body>
</html>`;

fs.writeFileSync(out, html);
console.log('Wrote ' + out + ' (' + Buffer.byteLength(html) + ' bytes)');
