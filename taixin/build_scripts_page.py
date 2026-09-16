#!/usr/bin/env python3
"""把 scripts/*.md 渲染成一个手机能翻的 HTML 页面（发布成 Artifact 用）。
用法: python build_scripts_page.py OUT.html
"""
import html
import json
import re
import sys
from pathlib import Path

from common import SCRIPT_DIR, load_videos

SECTIONS = ["主题", "三个 Hook 备选", "口播稿", "金句", "Carousel slogan 候选", "备注", "45 秒版"]


def parse(md: str) -> dict:
    d = {"title": "", "source": "", "sections": {}}
    m = re.search(r"^# (.+)$", md, re.M)
    d["title"] = m.group(1).strip() if m else ""
    m = re.search(r"灵感来源: (\S+)", md)
    d["source"] = m.group(1) if m else ""
    parts = re.split(r"^## ", md, flags=re.M)[1:]
    for p in parts:
        head, _, body = p.partition("\n")
        key = next((s for s in SECTIONS if head.startswith(s)), head.strip())
        d["sections"][key] = {"head": head.strip(), "body": body.strip()}
    d["skip"] = "不适合 Kenny" in md and "口播稿" not in d["sections"]
    s45 = d["sections"].get("45 秒版")
    m = re.search(r"tag:\s*(导流|互动)", s45["head"]) if s45 else None
    d["tag"] = m.group(1) if m else ""
    return d


def inline(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    return s


def render_body(key: str, body: str) -> str:
    lines = [l for l in body.splitlines()]
    out = []
    if key in ("口播稿", "45 秒版"):
        for l in lines:
            l = l.strip()
            if not l:
                continue
            m = re.match(r"\[([^\]]+)\]\s*(.*)", l)
            if m:
                out.append(f'<p class="line"><span class="tc">{inline(m.group(1))}</span>{inline(m.group(2))}</p>')
            else:
                out.append(f"<p>{inline(l)}</p>")
        return "".join(out)
    if key == "三个 Hook 备选":
        items = []
        for l in lines:
            m = re.match(r"\d\.\s*【([^】]+)】\s*(.*)", l.strip())
            if m:
                tag, text = m.groups()
                rec = "rec" if "推荐" in tag else ""
                items.append(f'<li class="{rec}"><span class="tag">{inline(tag)}</span>{inline(text)}</li>')
        return f'<ol class="hooks">{"".join(items)}</ol>'
    if key == "Carousel slogan 候选":
        items = []
        for l in lines:
            l = l.strip()
            if l:
                items.append("<li>" + inline(re.sub(r"^[A-C]\.\s*", "", l)) + "</li>")
        return f'<ul class="slogans">{"".join(items)}</ul>'
    if key == "备注":
        items = [f"<li>{inline(l.strip()[2:])}</li>" for l in lines if l.strip().startswith("- ")]
        return f'<ul class="notes">{"".join(items)}</ul>'
    return "".join(f"<p>{inline(l.strip())}</p>" for l in lines if l.strip())


def main(out: str) -> None:
    order = {v["id"]: i for i, v in enumerate(load_videos())}
    files = sorted((p for p in SCRIPT_DIR.glob("*.md") if p.name != "INDEX.md"), key=lambda p: order.get(p.stem, 9999))
    cards = []
    n_ok = n_skip = 0
    for i, p in enumerate(files, 1):
        d = parse(p.read_text(encoding="utf-8"))
        topic = d["sections"].get("主题", {}).get("body", "")
        quote = d["sections"].get("金句", {}).get("body", "")
        if d["skip"]:
            n_skip += 1
            reason = topic.replace("不适合 Kenny：", "").replace("不适合 Kenny:", "")
            cards.append(
                f'<article class="card skip" data-id="{p.stem}" data-text="{html.escape(topic)}">'
                f'<div class="card-head"><span class="num">{i:02d}</span><span class="pill">不适合</span></div>'
                f'<p class="topic">{inline(reason)}</p></article>'
            )
            continue
        n_ok += 1
        short = d["sections"].get("45 秒版")
        secs = ""
        if short:
            secs += f'<section class="s45"><h3>45 秒版 · {html.escape(d["tag"] or "")}</h3>{render_body("45 秒版", short["body"])}</section>'
        long_parts = "".join(
            f'<section><h3>{html.escape(d["sections"][k]["head"])}</h3>{render_body(k, d["sections"][k]["body"])}</section>'
            for k in ["三个 Hook 备选", "口播稿", "Carousel slogan 候选", "备注"] if k in d["sections"]
        )
        secs += f'<details class="long"><summary>长版（75 秒）· hook 备选 · slogan · 备注</summary>{long_parts}</details>' if short else long_parts
        search = html.escape(" ".join([topic, quote, d["sections"].get("三个 Hook 备选", {}).get("body", "")]))
        tag_pill = ('<span class="pill t-' + d["tag"] + '">' + d["tag"] + '</span>') if d["tag"] else ""
        cards.append(
            f'<article class="card" data-id="{p.stem}" data-tag="{d["tag"]}" data-text="{search}">'
            f'<button class="card-head" type="button" aria-expanded="false"><span class="num">{i:02d}</span>'
            f'<span class="quote">{inline(quote)}</span><span class="chev" aria-hidden="true"></span></button>'
            f'<p class="topic">{tag_pill}{inline(topic)}</p>'
            f'<div class="body" hidden>{secs}'
            f'<div class="actions"><button type="button" class="copy" data-target="{p.stem}">复制口播稿</button>'
            f'<a class="src" href="{html.escape(d["source"])}" target="_blank" rel="noopener">灵感来源</a></div></div>'
            f'</article>'
        )
    page = TEMPLATE.replace("{{CARDS}}", "\n".join(cards)).replace("{{N_OK}}", str(n_ok)).replace("{{N_SKIP}}", str(n_skip))
    Path(out).write_text(page, encoding="utf-8")
    print(f"{out}: {n_ok} 篇可用, {n_skip} 篇不适合, {len(page)//1024} KB")


TEMPLATE = r"""<title>宗臻口播稿库</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700;900&display=swap">
<style>
:root{
  --ink:#0f0f0e; --paper:#f7f6f1; --card:#ffffff; --muted:#6c6a62; --rule:#e4e1d6;
  --gold:#f5c518; --gold-ink:#1a1400; --soft:#faf7ea; --tag:#efece2;
  color-scheme:light;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --ink:#f2f0ea; --paper:#121211; --card:#1b1b19; --muted:#a6a39a; --rule:#2c2b28;
    --gold:#f5c518; --gold-ink:#1a1400; --soft:#23200f; --tag:#26251f; color-scheme:dark;
  }
}
:root[data-theme="dark"]{
  --ink:#f2f0ea; --paper:#121211; --card:#1b1b19; --muted:#a6a39a; --rule:#2c2b28;
  --gold:#f5c518; --gold-ink:#1a1400; --soft:#23200f; --tag:#26251f; color-scheme:dark;
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:"Noto Sans SC",-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;font-size:16px;line-height:1.7;-webkit-font-smoothing:antialiased}
.wrap{max-width:720px;margin:0 auto;padding-inline:16px;padding-block:0 48px}
header.top{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--paper);padding-block:14px 10px;border-bottom:1px solid var(--rule)}
.brand{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.brand h1{font-size:22px;font-weight:900;letter-spacing:-.01em;margin:0}
.brand .count{color:var(--muted);font-size:13px}
.bar{display:flex;gap:8px;margin-top:10px}
.bar input{flex:1;min-width:0;border:1px solid var(--rule);background:var(--card);color:var(--ink);border-radius:10px;padding:9px 12px;font:inherit;font-size:15px}
.bar input:focus{outline:2px solid var(--gold);outline-offset:1px}
.filters{display:flex;gap:6px;margin-top:8px}
.filters button{border:1px solid var(--rule);background:var(--card);color:var(--muted);border-radius:999px;padding:4px 12px;font:inherit;font-size:13px;cursor:pointer}
.filters button[aria-pressed="true"]{background:var(--ink);color:var(--paper);border-color:var(--ink)}
.filters button:focus-visible,.card-head:focus-visible,.copy:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
.list{display:flex;flex-direction:column;gap:10px;margin-top:14px}
.card{background:var(--card);border:1px solid var(--rule);border-radius:14px;padding:12px 14px 12px}
.card-head{display:flex;align-items:flex-start;gap:10px;width:100%;background:none;border:0;padding:0;color:inherit;font:inherit;text-align:left;cursor:pointer}
.num{font-size:12px;color:var(--muted);letter-spacing:.08em;padding-top:5px;font-variant-numeric:tabular-nums;flex:0 0 auto}
.quote{font-weight:900;font-size:18px;line-height:1.35;flex:1;text-wrap:balance}
.chev{flex:0 0 auto;width:10px;height:10px;margin-top:8px;border-right:2px solid var(--muted);border-bottom:2px solid var(--muted);transform:rotate(45deg);transition:transform .15s}
.card-head[aria-expanded="true"] .chev{transform:rotate(-135deg);margin-top:12px}
.topic{margin:6px 0 0 0;color:var(--muted);font-size:14px;line-height:1.6}
.card.skip{opacity:.7}
.card.skip .card-head{cursor:default}
.pill{font-size:11px;letter-spacing:.08em;padding:2px 8px;border-radius:999px;background:var(--tag);color:var(--muted);margin-right:6px;vertical-align:1px}
.pill.t-导流{background:var(--gold);color:var(--gold-ink)}
.s45 .line{font-size:17px}
details.long{margin-top:6px;border-top:1px solid var(--rule)}
details.long summary{cursor:pointer;font-size:13px;color:var(--muted);padding:10px 0;list-style:none}
details.long summary::before{content:"▸ ";}
details.long[open] summary::before{content:"▾ ";}
details.long section:first-of-type{border-top:0}
.body{margin-top:12px;border-top:1px dashed var(--rule);padding-top:4px}
section{padding-block:10px}
section+section{border-top:1px solid var(--rule)}
h3{font-size:12px;letter-spacing:.14em;color:var(--muted);font-weight:700;margin:0 0 6px 0;text-transform:uppercase}
.hooks{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px}
.hooks li{padding:8px 10px;border-radius:8px;background:var(--tag);font-size:15px;line-height:1.5}
.hooks li.rec{background:var(--soft);box-shadow:inset 3px 0 0 var(--gold)}
.tag{display:inline-block;font-size:11px;color:var(--muted);margin-right:8px;letter-spacing:.04em}
.line{margin:0 0 10px 0;font-size:16px}
.tc{display:block;font-size:11px;color:var(--muted);letter-spacing:.06em;font-variant-numeric:tabular-nums;margin-bottom:1px}
.slogans{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:4px}
.slogans li{padding:6px 10px;border-radius:8px;background:var(--gold);color:var(--gold-ink);font-weight:700;font-size:15px;width:fit-content;max-width:100%}
.notes{margin:0;padding-left:18px;color:var(--muted);font-size:13px;line-height:1.6}
.actions{display:flex;gap:10px;align-items:center;padding-top:10px;flex-wrap:wrap}
.copy{border:0;background:var(--ink);color:var(--paper);border-radius:999px;padding:8px 16px;font:inherit;font-size:14px;font-weight:700;cursor:pointer}
.src{font-size:13px;color:var(--muted)}
.empty{color:var(--muted);text-align:center;padding:40px 0;display:none}
@media (prefers-reduced-motion: reduce){.chev{transition:none}}
</style>
<div class="wrap">
<header class="top">
  <div class="brand"><h1>宗臻口播稿库</h1><span class="count">{{N_OK}} 篇 · 先看 45 秒版，展开看长版</span></div>
  <div class="bar"><input id="q" type="search" placeholder="搜主题、金句、hook" autocomplete="off"></div>
  <div class="filters" role="group" aria-label="筛选">
    <button type="button" data-f="ok" aria-pressed="true" id="f-ok">可用</button>
    <button type="button" data-f="导流" aria-pressed="false" id="f-lead">导流</button>
    <button type="button" data-f="互动" aria-pressed="false" id="f-eng">互动</button>
    <button type="button" data-f="all" aria-pressed="false" id="f-all">全部</button>
  </div>
</header>
<main class="list" id="list">
{{CARDS}}
</main>
<p class="empty" id="empty">没有匹配的稿子</p>
</div>
<script>
(function(){
  var list=document.getElementById('list'), q=document.getElementById('q'), empty=document.getElementById('empty');
  var mode='ok';
  try{ var m=localStorage.getItem('kenny-scripts-filter'); if(m==='all'||m==='ok'||m==='导流'||m==='互动') mode=m; }catch(e){}
  function setMode(v){ mode=v; document.querySelectorAll('.filters button').forEach(function(b){b.setAttribute('aria-pressed', b.dataset.f===v?'true':'false');}); try{localStorage.setItem('kenny-scripts-filter',v);}catch(e){} apply(); }
  function apply(){
    var t=(q.value||'').trim().toLowerCase(), shown=0;
    list.querySelectorAll('.card').forEach(function(c){
      var pass = mode==='all' ? true : mode==='ok' ? !c.classList.contains('skip') : (c.dataset.tag===mode);
      var ok = pass && (!t || (c.dataset.text||'').toLowerCase().indexOf(t)>=0);
      c.hidden=!ok; if(ok) shown++;
    });
    empty.style.display = shown?'none':'block';
  }
  document.querySelectorAll('.filters button').forEach(function(b){ b.addEventListener('click', function(){ setMode(b.dataset.f); }); });
  q.addEventListener('input', apply);
  list.addEventListener('click', function(e){
    var head=e.target.closest('.card-head'); 
    if(head && head.tagName==='BUTTON'){ var body=head.parentElement.querySelector('.body'); var open=head.getAttribute('aria-expanded')==='true'; head.setAttribute('aria-expanded', open?'false':'true'); body.hidden=open; return; }
    var cp=e.target.closest('.copy');
    if(cp){ var card=cp.closest('.card'); var lines=[]; (card.querySelector('.s45')||card).querySelectorAll('.line').forEach(function(p){ lines.push(p.textContent.replace(/^([0-9:–\-结尾]+)\s*/,'').trim()); });
      var text=lines.join('\n\n');
      var done=function(){ cp.textContent='已复制'; setTimeout(function(){cp.textContent='复制口播稿';},1500); };
      if(navigator.clipboard&&navigator.clipboard.writeText){ navigator.clipboard.writeText(text).then(done, function(){ cp.textContent='复制失败，长按选取'; }); }
      else { cp.textContent='长按文字选取复制'; }
    }
  });
  setMode(mode);
})();
</script>
"""

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "scripts_page.html")
