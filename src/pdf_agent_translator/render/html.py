# -*- coding: utf-8 -*-
"""离线双语阅读器。

\\file 审阅用分块；学习用整篇。左侧目录来自 outline。表格/代码在前端按 GFM 渲染。
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from pdf_agent_translator.models import Document

_CSS = r"""
:root {
  --bg: #f3efe6;
  --paper: #fffcf6;
  --ink: #1c1917;
  --muted: #78716c;
  --line: #e7e0d4;
  --accent: #0f766e;
  --accent-soft: #ccfbf1;
  --src-bg: #f5f5f4;
  --tgt-bg: #ecfeff;
  --sidebar: #1c1917;
  --sidebar-ink: #e7e5e4;
  --code-bg: #1e293b;
  --code-ink: #e2e8f0;
  --review-bg: #eef2f6;
}
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; }
body {
  font-family: "Iwanami", "Source Han Serif SC", "Noto Serif SC", "Songti SC", Georgia, serif;
  color: var(--ink);
  background: var(--bg);
}
.app { display: flex; min-height: 100%; }
.sidebar {
  width: 268px;
  flex: 0 0 268px;
  background: var(--sidebar);
  color: var(--sidebar-ink);
  padding: 12px 0 32px;
  position: sticky;
  top: 0;
  height: 100vh;
  overflow: auto;
  font-family: "Segoe UI", "PingFang SC", sans-serif;
  transition: flex-basis .18s ease, width .18s ease;
}
.sidebar-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 4px 10px 10px 16px;
}
.sidebar h2 {
  margin: 0;
  font-size: 12px;
  letter-spacing: .14em;
  text-transform: uppercase;
  color: #a8a29e;
  font-weight: 600;
}
.icon-btn {
  border: 0; background: transparent; color: #a8a29e; cursor: pointer;
  width: 28px; height: 28px; border-radius: 6px; padding: 0; line-height: 28px;
  font-size: 16px;
}
.icon-btn:hover { background: #292524; color: #fff; }
body.nav-folded .sidebar {
  width: 44px; flex-basis: 44px; overflow: hidden;
}
body.nav-folded .sidebar h2,
body.nav-folded .toc { display: none; }
body.nav-folded .sidebar-head { padding: 8px 8px; justify-content: center; }
#nav-reopen {
  display: none; margin-right: 4px;
  color: #44403c; border: 1px solid #d6d3d1; background: #fff;
  width: 32px; font-size: 14px;
}
body.nav-folded #nav-reopen { display: inline-flex; }
.toc-row { display: flex; align-items: flex-start; }
.toc-twist {
  flex: 0 0 18px; width: 18px; height: 22px; margin: 4px 0 0 6px;
  border: 0; background: transparent; color: #78716c; cursor: pointer;
  padding: 0; font-size: 10px; line-height: 22px;
}
.toc-twist:hover { color: #fff; }
.toc-twist.leaf { visibility: hidden; cursor: default; }
.toc a {
  display: block; flex: 1; min-width: 0;
  color: #d6d3d1;
  text-decoration: none;
  padding: 6px 14px 6px 4px;
  border-left: 3px solid transparent;
  line-height: 1.35;
  font-size: 13px;
}
.toc a:hover { color: #fff; }
.toc-row:hover { background: #292524; }
.toc a.active { border-left-color: #2dd4bf; color: #fff; }
.toc .lv1 > .toc-row a { font-weight: 700; font-size: 14px; padding-top: 8px; }
.toc .lv2 > .toc-row a { font-size: 13px; }
.toc .lv3 > .toc-row a { font-size: 12px; color: #a8a29e; }
.toc .lv4 > .toc-row a { font-size: 12px; color: #78716c; }
.toc-node.folded > .toc-kids { display: none; }
.toc-node.folded > .toc-row .toc-twist { transform: rotate(-90deg); }
.main { flex: 1; min-width: 0; }
.toolbar {
  position: sticky; top: 0; z-index: 5;
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
  padding: 12px 22px;
  background: rgba(243,239,230,.92);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--line);
  font-family: "Segoe UI", "PingFang SC", sans-serif;
  font-size: 13px;
}
.toolbar .doc-title { font-weight: 650; margin-right: auto; max-width: 42%;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
button, select, label { font: inherit; }
button {
  border: 1px solid #d6d3d1; background: #fff; border-radius: 8px;
  padding: 6px 10px; cursor: pointer;
}
button.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
button:hover { filter: brightness(.97); }
label.chk { display: inline-flex; align-items: center; gap: 6px; color: #44403c; }
.content { padding: 20px 28px 64px; }
.meta-line { color: var(--muted); font-size: 12px; margin: 0 0 16px;
  font-family: "Segoe UI", sans-serif; }
.block {
  position: relative;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 12px;
  margin: 0 0 14px;
  padding: 14px 16px 16px;
  box-shadow: 0 1px 0 rgba(28,25,23,.04);
}
.block-meta { color: var(--muted); font-size: 12px; margin-bottom: 8px;
  font-family: "Segoe UI", sans-serif; }
.tag { display: inline-block; background: #f5f5f4; border-radius: 999px;
  padding: 1px 8px; margin-left: 6px; }
.src { background: var(--src-bg); border-radius: 8px; padding: 10px 12px; margin-bottom: 8px; }
.tgt { background: var(--tgt-bg); border-radius: 8px; padding: 10px 12px; }
.float { position: absolute; right: 8px; top: 8px; display: flex; flex-direction: column; gap: 4px; }
.float button { padding: 3px 7px; font-size: 11px; }
textarea { width: 100%; min-height: 110px; font: 14px/1.5 ui-monospace, Consolas, monospace;
  border: 1px solid var(--line); border-radius: 8px; padding: 8px; }
.edit-actions { margin-top: 8px; display: flex; gap: 8px; }
.article {
  /* 单栏阅读：按主栏可用宽度铺开，上限 56rem（约 896px），不再锁在 38rem。 */
  max-width: min(56rem, calc(100% - 8px));
  margin: 0 auto;
  background: var(--paper);
  padding: 48px 56px 72px;
  border-radius: 2px;
  box-shadow: 0 10px 40px rgba(28,25,23,.06);
}
.article.compare-side {
  max-width: min(80rem, 100%);
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 36px;
  padding: 36px 40px 64px;
}
.article.compare-stack { max-width: min(56rem, calc(100% - 8px)); }
.article .md, .pair-chunk { font-size: 18px; line-height: 1.75; }
.article .md h1, .pair-chunk h1 { font-size: 1.85em; line-height: 1.25; margin: 0 0 .8em; }
.article .md h2, .pair-chunk h2 { font-size: 1.35em; margin: 1.4em 0 .45em; padding-bottom: .2em;
  border-bottom: 1px solid var(--line); }
.article .md h3, .pair-chunk h3 { font-size: 1.12em; margin: 1.15em 0 .35em; }
.article .md p, .md p, .pair-chunk p { margin: 0 0 .55em; }
.pair-unit { margin: 0 0 1.15em; padding: .15em .35em; border-radius: 8px; }
/* 解析器把每条 • 拆成独立块；连续列表项不能再套段落级下边距。 */
.pair-unit.is-list { margin-bottom: .15em; }
.pair-unit.is-list + .pair-unit.is-list { margin-top: 0; }
.pair-unit.is-figure { margin-bottom: .25em; text-align: center; }
.pair-unit.is-figure + .pair-unit.is-caption { margin-top: 0; }
.pair-unit.is-caption { margin: 0 0 1.35em; }
.pair-chunk.fig-image img { margin: 6px auto 4px; max-width: min(100%, 38rem); }
.pair-chunk.fig-caption,
.md.fig-caption {
  text-align: center;
  font-size: 14px;
  line-height: 1.55;
  color: #57534e;
  font-family: "Segoe UI", "PingFang SC", "Noto Sans SC", sans-serif;
  font-style: italic;
  max-width: 40rem;
  margin: 0 auto;
}
.pair-chunk.fig-caption p, .md.fig-caption p { margin: 0; }
.cap-label { font-style: normal; font-weight: 650; color: #292524; margin-right: .15em; }
.pair-chunk ul, .pair-chunk ol, .md ul, .md ol {
  margin: .15em 0; padding-left: 1.35em;
}
.pair-chunk li, .md li { margin: .12em 0; }
.pair-chunk.src-line { color: #44403c; }
.pair-chunk.tgt-line { color: #0f766e; }
.compare-stack .pair-chunk.tgt-line { margin-top: .15em; font-size: 17px; line-height: 1.7; }
.compare-stack .pair-unit.pair-hot {
  background: rgba(13,148,136,.08);
  box-shadow: inset 3px 0 0 #0d9488;
}
.compare-side .col { min-width: 0; }
.compare-side .pair-chunk { padding: .2em .4em; border-radius: 6px; }
.compare-side .pair-chunk.pair-hot {
  background: rgba(13,148,136,.12);
  outline: 1px solid rgba(13,148,136,.25);
}
.block .src.pair-hot, .block .tgt.pair-hot { outline: 2px solid rgba(13,148,136,.45); }
.md { word-break: break-word; }
.md img { max-width: 100%; height: auto; display: block; margin: 12px auto; }
.md table, .pair-chunk table {
  border-collapse: collapse; width: 100%; margin: 14px 0 18px;
  font-size: 14px; font-family: "Segoe UI", "PingFang SC", sans-serif;
  background: #fff;
}
.md th, .md td, .pair-chunk th, .pair-chunk td {
  border: 1px solid #d6d3d1; padding: 6px 8px; text-align: left; vertical-align: top;
}
.md th, .pair-chunk th { background: #f5f5f4; font-weight: 650; }
.md tr:nth-child(even) td, .pair-chunk tr:nth-child(even) td { background: #fafaf9; }
.md pre {
  background: var(--code-bg); color: var(--code-ink);
  padding: 12px 14px; border-radius: 8px; overflow: auto;
  font: 13px/1.5 ui-monospace, Consolas, monospace; margin: 12px 0;
}
.md code { font-family: ui-monospace, Consolas, monospace; font-size: .92em; }
.md :not(pre) > code { background: #f5f5f4; padding: 1px 5px; border-radius: 4px; }
.math, .pair-chunk .math {
  font-family: "Cambria Math", "Latin Modern Math", "Times New Roman", Times, serif;
  font-style: italic;
  white-space: nowrap;
  padding: 0 .08em;
}
.math .mathrm { font-style: normal; font-family: inherit; }
.math .mathcal { font-style: italic; }
.math.display { display: block; text-align: center; margin: .7em 0; white-space: normal; }
body.review { background: var(--review-bg); }
body.review .toolbar { background: rgba(238,242,246,.94); }
.toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
  background: #1c1917; color: #fff; padding: 8px 14px; border-radius: 8px; display: none;
  font-family: "Segoe UI", sans-serif; }
@media (max-width: 900px) {
  .sidebar { display: none; }
  .article { padding: 28px 20px 48px; }
  .article.compare-side { grid-template-columns: 1fr; }
}
"""

_JS = r"""
const DATA = JSON.parse(document.getElementById('doc-data').textContent);
let viewMode = 'translation';
let compareFirst = 'source';
let compareLayout = 'stack';
let editMode = false;
const toastEl = document.getElementById('toast');

function esc(s){
  return String(s||'').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
}
function isSepRow(line){
  const cells = line.trim().replace(/^\|/,'').replace(/\|$/,'').split('|');
  return cells.length>0 && cells.every(c => /^:?-{2,}:?$/.test(c.trim()) || c.trim()==='');
}
function isPipeRow(line){ return /\|/.test(line); }
function rowCells(line){
  return line.trim().replace(/^\|/,'').replace(/\|$/,'').split('|').map(c => c.trim());
}
function tableHtml(rows){
  if (!rows.length) return '';
  let html = '<table><thead><tr>';
  for (const c of rowCells(rows[0])) html += `<th>${inlineMd(c)}</th>`;
  html += '</tr></thead><tbody>';
  const start = (rows.length>1 && isSepRow(rows[1])) ? 2 : 1;
  for (let i=start;i<rows.length;i++){
    if (isSepRow(rows[i])) continue;
    html += '<tr>';
    for (const c of rowCells(rows[i])) html += `<td>${inlineMd(c)}</td>`;
    html += '</tr>';
  }
  return html + '</tbody></table>';
}
function latexToHtml(src){
  const SYM = {
    times:'×', cdot:'·', ge:'≥', geq:'≥', le:'≤', leq:'≤', neq:'≠', ne:'≠',
    approx:'≈', infty:'∞', pm:'±', ldots:'…', dots:'…', cdots:'⋯',
    alpha:'α', beta:'β', gamma:'γ', delta:'δ', mu:'μ', pi:'π', sigma:'σ', omega:'ω',
    ell:'ℓ', left:'', right:''
  };
  let s = esc(String(src||''));
  s = s.replace(/\\_/g, '\uE000');
  s = s.replace(/\\text\{([^}]*)\}/g, (_,t) => `<span class="mathrm">${esc(t)}</span>`);
  s = s.replace(/\\mathrm\{([^}]*)\}/g, (_,t) => `<span class="mathrm">${esc(t)}</span>`);
  s = s.replace(/\\mathcal\{([^}]*)\}/g, (_,t) => `<span class="mathcal">${esc(t)}</span>`);
  s = s.replace(/\\([A-Za-z]+)/g, (m, name) => SYM[name] !== undefined ? SYM[name] : m);
  s = s.replace(/\\\{/g, '{').replace(/\\\}/g, '}');
  s = s.replace(/\^\{([^}]+)\}/g, (_,t) => `<sup>${t}</sup>`);
  s = s.replace(/\^(\w)/g, (_,t) => `<sup>${t}</sup>`);
  s = s.replace(/_\{([^}]+)\}/g, (_,t) => `<sub>${t}</sub>`);
  s = s.replace(/\uE000/g, '_');
  return s;
}
function inlineMd(t){
  const slots = [];
  let raw = String(t||'');
  raw = raw.replace(/\$\$([\s\S]+?)\$\$/g, (_,m) => {
    slots.push(`<span class="math display">${latexToHtml(m)}</span>`);
    return `\uE001${slots.length-1}\uE001`;
  });
  raw = raw.replace(/\$([^$\n]+)\$/g, (_,m) => {
    slots.push(`<span class="math">${latexToHtml(m)}</span>`);
    return `\uE001${slots.length-1}\uE001`;
  });
  let html = esc(raw);
  html = html.replace(/\uE001(\d+)\uE001/g, (_,i) => slots[+i]);
  html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_,a,u) => `<img alt="${a}" src="${u}">`);
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
  return html;
}
function mdToHtml(src, headingPrefix){
  let text = String(src||'').replace(/\r\n/g,'\n');
  text = text.replace(/^``([A-Za-z0-9_+-]+)\s*$/gm, '```$1');
  const lines = text.split('\n');
  const out = [];
  let i = 0;
  while (i < lines.length){
    const line = lines[i];
    const fence = line.trim().match(/^```([\w+-]*)\s*$/);
    if (fence){
      const buf = [];
      i++;
      while (i < lines.length && !/^```\s*$/.test(lines[i].trim())){
        buf.push(lines[i]); i++;
      }
      if (i < lines.length) i++;
      out.push(`<pre><code>${esc(buf.join('\n'))}</code></pre>`);
      continue;
    }
    if (isPipeRow(line)){
      const rows = [];
      while (i < lines.length && (isPipeRow(lines[i]) || lines[i].trim()==='')){
        if (lines[i].trim()!=='') rows.push(lines[i]);
        else if (rows.length>=2) break;
        i++;
      }
      if (rows.length>=2){ out.push(tableHtml(rows)); continue; }
      out.push(lines[i-1] || line);
      continue;
    }
    const hm = line.match(/^(#{1,6})\s+(.*)$/);
    if (hm){
      const lv = hm[1].length;
      const id = headingPrefix ? `${headingPrefix}${slug(hm[2])}` : slug(hm[2]);
      out.push(`<h${lv} id="${esc(id)}">${inlineMd(hm[2])}</h${lv}>`);
      i++; continue;
    }
    if (/^\s*[-*•]\s+/.test(line)){
      const items = [];
      while (i < lines.length && /^\s*[-*•]\s+/.test(lines[i])){
        items.push('<li>'+inlineMd(lines[i].replace(/^\s*[-*•]\s+/,''))+'</li>');
        i++;
      }
      out.push('<ul>'+items.join('')+'</ul>');
      continue;
    }
    if (line.trim()===''){ out.push(''); i++; continue; }
    const para = [];
    while (i < lines.length && lines[i].trim()!=='' && !isPipeRow(lines[i]) && !lines[i].trim().startsWith('#') && !lines[i].trim().startsWith('```')){
      para.push(lines[i]); i++;
    }
    out.push('<p>'+inlineMd(para.join('\n'))+'</p>');
  }
  return out.join('\n');
}
function slug(s){
  return String(s||'').trim().toLowerCase().replace(/\s+/g,'-').replace(/[^\w\u4e00-\u9fff-]+/g,'').slice(0,48);
}
function showToast(msg){
  toastEl.textContent = msg;
  toastEl.style.display = 'block';
  setTimeout(() => toastEl.style.display = 'none', 1600);
}
function counts(){
  const c = {translated:0,skipped:0,failed:0,pending:0,edited:0};
  for (const p of DATA.pairs){ if (c[p.target.status]!==undefined) c[p.target.status]++; else c.pending++; }
  return c;
}
function pickMd(p, which){
  if (which==='source') return p.source.markdown||'';
  return (p.target.markdown || p.source.markdown || '');
}
function headingId(blockId){ return 'sec-'+blockId; }
const foldedIds = new Set();
function outlineTree(list){
  const root = [];
  const stack = [];
  (list||[]).forEach(e => {
    const node = {block_id:e.block_id, level:e.level||1, title:e.title||e.source_title||'', children:[]};
    while (stack.length && stack[stack.length-1].level >= node.level) stack.pop();
    if (!stack.length) root.push(node); else stack[stack.length-1].children.push(node);
    stack.push(node);
  });
  return root;
}
function tocNodeHtml(node){
  const kids = node.children||[];
  const leaf = kids.length===0;
  const folded = foldedIds.has(node.block_id);
  return `<div class="toc-node lv${node.level}${folded?' folded':''}" data-bid="${esc(node.block_id)}">
    <div class="toc-row">
      <button type="button" class="toc-twist${leaf?' leaf':''}" data-fold="${esc(node.block_id)}" aria-expanded="${leaf? 'true': String(!folded)}">${leaf?'•':'▾'}</button>
      <a href="#${headingId(node.block_id)}" data-bid="${esc(node.block_id)}">${esc(node.title)}</a>
    </div>
    ${leaf?'':`<div class="toc-kids">${kids.map(tocNodeHtml).join('')}</div>`}
  </div>`;
}
function renderToc(){
  const box = document.getElementById('toc');
  const outline = DATA.outline || [];
  if (!outline.length){ box.innerHTML = '<div style="padding:8px 18px;color:#78716c">暂无目录</div>'; return; }
  box.innerHTML = outlineTree(outline).map(tocNodeHtml).join('');
}
function setNavFolded(on){
  document.body.classList.toggle('nav-folded', on);
  try { localStorage.setItem('pat-nav-folded', on ? '1' : '0'); } catch (e) {}
  const btn = document.getElementById('nav-toggle');
  if (btn) btn.title = on ? '展开目录' : '收起目录';
}
function pairRoles(){
  const first = compareFirst==='source' ? 'source' : 'target';
  return [first, first==='source' ? 'target' : 'source'];
}
function isListMd(md){
  const lines = String(md||'').split('\n').map(s => s.trim()).filter(Boolean);
  return lines.length>0 && lines.every(ln => /^[-*•]\s+/.test(ln));
}
function isCaptionType(p){
  const t = ((p.source && p.source.type) || '').toLowerCase();
  return t==='figure_name' || t==='figure_note' || t==='table_name' || t==='table_note';
}
function isFigureType(p){ return ((p.source && p.source.type) || '')==='figure'; }
function unitKindClass(p, md){
  if (isFigureType(p)) return ' is-figure';
  if (isCaptionType(p)) return ' is-caption';
  if (isListMd(md)) return ' is-list';
  return '';
}
function captionMd(md){
  return String(md||'').replace(/^\s*>\s?/gm, '').trim();
}
function markCaptionLabel(html){
  return html.replace(
    /(<p>)((?:图|表|Fig\.?|Figure|TABLE|Table|Listing|Listings|代码清单)\s*[0-9IVXLCDM]+[.:：]?\s*)/i,
    '$1<span class="cap-label">$2</span>'
  );
}
function chunkHtml(p, i, which){
  const role = which==='source' ? 'src-line' : 'tgt-line';
  let md = pickMd(p, which);
  let extra = '';
  if (isCaptionType(p)){
    extra = ' fig-caption';
    md = captionMd(md);
  } else if (isFigureType(p)){
    extra = ' fig-image';
  }
  let inner = mdToHtml(md);
  if (isCaptionType(p)) inner = markCaptionLabel(inner);
  return `<div class="pair-chunk ${role}${extra}" data-pair="${i}">${inner}</div>`;
}
function bindPairHover(root){
  root.addEventListener('mouseover', ev => {
    const el = ev.target.closest('[data-pair]');
    if (!el) return;
    const id = el.getAttribute('data-pair');
    root.querySelectorAll('[data-pair]').forEach(n => {
      n.classList.toggle('pair-hot', n.getAttribute('data-pair')===id);
    });
  });
  root.addEventListener('mouseleave', () => {
    root.querySelectorAll('.pair-hot').forEach(n => n.classList.remove('pair-hot'));
  });
}
function renderArticle(){
  const list = document.getElementById('list');
  list.className = 'content';
  const wrap = document.createElement('div');
  if (viewMode!=='compare'){
    wrap.className = 'article';
    const which = viewMode==='parse' ? 'source' : 'target';
    wrap.innerHTML = DATA.pairs.map((p,i) => {
      const hid = p.source.type==='title' ? ` id="${headingId(p.source.block_id)}"` : '';
      const kind = unitKindClass(p, pickMd(p, which));
      return `<div class="pair-unit${kind}"${hid} data-pair="${i}">${chunkHtml(p,i,which)}</div>`;
    }).join('');
  } else if (compareLayout==='side'){
    wrap.className = 'article compare-side';
    const [a,b] = pairRoles();
    const left = DATA.pairs.map((p,i) => {
      const hid = p.source.type==='title' ? ` id="${headingId(p.source.block_id)}"` : '';
      return `<div${hid}>${chunkHtml(p,i,a)}</div>`;
    }).join('');
    const right = DATA.pairs.map((p,i) => chunkHtml(p,i,b)).join('');
    wrap.innerHTML = `<div class="col">${left}</div><div class="col">${right}</div>`;
  } else {
    // 豆包/沉浸式翻译式：一段原文，紧跟一段译文。
    wrap.className = 'article compare-stack';
    const [a,b] = pairRoles();
    wrap.innerHTML = DATA.pairs.map((p,i) => {
      const hid = p.source.type==='title' ? ` id="${headingId(p.source.block_id)}"` : '';
      const kind = unitKindClass(p, pickMd(p,a)) || unitKindClass(p, pickMd(p,b));
      return `<div class="pair-unit${kind}" data-pair="${i}"${hid}>${chunkHtml(p,i,a)}${chunkHtml(p,i,b)}</div>`;
    }).join('');
  }
  list.innerHTML = '';
  list.appendChild(wrap);
  bindPairHover(wrap);
}
function renderBlocks(){
  const list = document.getElementById('list');
  list.className = 'content';
  list.innerHTML = '';
  DATA.pairs.forEach((p, i) => {
    const src = p.source, tgt = p.target;
    const page = (src.page_num==null) ? '-' : (src.page_num + 1);
    const wrap = document.createElement('div');
    wrap.className = 'block' + (isCaptionType(p) ? ' is-caption' : '') + (isFigureType(p) ? ' is-figure' : '');
    wrap.id = headingId(src.block_id);
    const srcMd = isCaptionType(p) ? captionMd(src.markdown) : src.markdown;
    const tgtMd = isCaptionType(p) ? captionMd(tgt.markdown || src.markdown) : (tgt.markdown || src.markdown);
    const capCls = isCaptionType(p) ? ' fig-caption' : '';
    const srcHtml = `<div class="src md${capCls}" data-pair="${i}">${isCaptionType(p)?markCaptionLabel(mdToHtml(srcMd)):mdToHtml(srcMd)}</div>`;
    const tgtHtml = `<div class="tgt md${capCls}" data-pair="${i}">${isCaptionType(p)?markCaptionLabel(mdToHtml(tgtMd)):mdToHtml(tgtMd)}</div>`;
    let body = srcHtml;
    if (viewMode==='translation') body = tgtHtml;
    else if (viewMode==='compare') body = compareFirst==='source' ? srcHtml+tgtHtml : tgtHtml+srcHtml;
    wrap.innerHTML = `
      <div class="block-meta">第 ${page} 页 <span class="tag">${esc(src.type)}</span>
        ${src.sub_type?`<span class="tag">${esc(src.sub_type)}</span>`:''}
        <span class="tag">${esc(tgt.status)}</span></div>
      <div class="body">${body}</div>
      <div class="float">
        <button data-act="es" data-i="${i}">编原文</button>
        <button data-act="et" data-i="${i}">编译文</button>
      </div>`;
    list.appendChild(wrap);
  });
  bindPairHover(list);
}
function render(){
  document.body.classList.toggle('review', editMode);
  const c = counts();
  document.getElementById('counts').textContent =
    `translated ${c.translated} · skipped ${c.skipped} · failed ${c.failed} · pending ${c.pending}`;
  document.getElementById('cmp').disabled = viewMode!=='compare';
  document.getElementById('layout').disabled = viewMode!=='compare' || editMode;
  if (editMode) renderBlocks(); else renderArticle();
}
function startEdit(i, which){
  const p = DATA.pairs[i];
  const wrap = document.querySelectorAll('.block')[i];
  if (!wrap) return;
  const val = which==='source' ? p.source.markdown : (p.target.markdown||'');
  const area = document.createElement('div');
  area.innerHTML = `<textarea></textarea>
    <div class="edit-actions"><button class="primary" data-save="${which}" data-i="${i}">保存</button>
    <button data-cancel="1">取消</button></div>`;
  area.querySelector('textarea').value = val;
  wrap.querySelector('.body').prepend(area);
}
document.getElementById('list').addEventListener('click', ev => {
  const btn = ev.target.closest('button');
  if (!btn) return;
  if (btn.dataset.act==='es') startEdit(+btn.dataset.i,'source');
  if (btn.dataset.act==='et') startEdit(+btn.dataset.i,'translation');
  if (btn.dataset.save){
    const i = +btn.dataset.i;
    const text = btn.closest('div').parentElement.querySelector('textarea').value;
    if (btn.dataset.save==='source'){ DATA.pairs[i].source.markdown = text; DATA.pairs[i].source.edited = true; }
    else { DATA.pairs[i].target.markdown = text; DATA.pairs[i].target.edited = true; DATA.pairs[i].target.status='edited'; }
    render(); showToast('已改内存中的文档，请下载 JSON/HTML 保存');
  }
  if (btn.dataset.cancel) render();
});
document.getElementById('toc').addEventListener('click', ev => {
  const twist = ev.target.closest('[data-fold]');
  if (twist && !twist.classList.contains('leaf')){
    ev.preventDefault();
    const id = twist.getAttribute('data-fold');
    if (foldedIds.has(id)) foldedIds.delete(id); else foldedIds.add(id);
    const node = twist.closest('.toc-node');
    if (node){
      node.classList.toggle('folded', foldedIds.has(id));
      twist.setAttribute('aria-expanded', String(!foldedIds.has(id)));
    }
    return;
  }
  const a = ev.target.closest('a');
  if (!a) return;
  ev.preventDefault();
  const el = document.getElementById(a.getAttribute('href').slice(1));
  if (el) el.scrollIntoView({behavior:'smooth', block:'start'});
  document.querySelectorAll('.toc a').forEach(x => x.classList.toggle('active', x===a));
});
document.getElementById('nav-toggle').addEventListener('click', () => {
  setNavFolded(!document.body.classList.contains('nav-folded'));
});
document.getElementById('nav-reopen').addEventListener('click', () => setNavFolded(false));
function download(name, blob){
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 800);
}
document.getElementById('mode').addEventListener('change', e => { viewMode = e.target.value; render(); });
document.getElementById('cmp').addEventListener('change', e => { compareFirst = e.target.value; render(); });
document.getElementById('layout').addEventListener('change', e => { compareLayout = e.target.value; render(); });
document.getElementById('edit-mode').addEventListener('change', e => { editMode = e.target.checked; render(); });
document.getElementById('dl-json').addEventListener('click', () => {
  download((DATA.source_pdf_name||'document')+'.translated.json',
    new Blob([JSON.stringify(DATA,null,2)], {type:'application/json'}));
});
document.getElementById('dl-html').addEventListener('click', () => {
  const clone = document.documentElement.cloneNode(true);
  const script = clone.querySelector('#doc-data');
  if (script) script.textContent = JSON.stringify(DATA);
  download((DATA.source_pdf_name||'document')+'.html',
    new Blob(['<!DOCTYPE html>\n'+clone.outerHTML], {type:'text/html'}));
});
try { if (localStorage.getItem('pat-nav-folded')==='1') setNavFolded(true); } catch (e) {}
renderToc();
render();
"""


def render_html(document: Document, dest: Path) -> Path:
    """把 Document 写成单文件阅读器。"""

    payload = json.dumps(document.model_dump(mode="json"), ensure_ascii=False)
    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{html.escape(document.source_pdf_name)} · 双语阅读</title>
<style>{_CSS}</style>
</head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="sidebar-head">
      <h2>目录</h2>
      <button type="button" class="icon-btn" id="nav-toggle" title="收起目录">«</button>
    </div>
    <nav id="toc" class="toc"></nav>
  </aside>
  <div class="main">
    <div class="toolbar">
      <button type="button" class="icon-btn" id="nav-reopen" title="展开目录">☰</button>
      <div class="doc-title">{html.escape(document.source_pdf_name)}</div>
      <select id="mode">
        <option value="parse">解析结果</option>
        <option value="translation" selected>翻译结果</option>
        <option value="compare">双语对照</option>
      </select>
      <select id="cmp">
        <option value="source">原文在前</option>
        <option value="target">译文在前</option>
      </select>
      <select id="layout">
        <option value="stack" selected>上下对照</option>
        <option value="side">左右对照</option>
      </select>
      <label class="chk"><input id="edit-mode" type="checkbox"/> 编辑模式</label>
      <button class="primary" id="dl-json" type="button">下载 JSON</button>
      <button id="dl-html" type="button">下载 HTML</button>
    </div>
    <div id="counts" class="meta-line"></div>
    <div id="list" class="content"></div>
  </div>
</div>
<script type="application/json" id="doc-data">{payload}</script>
<div class="toast" id="toast"></div>
<script>{_JS}</script>
</body>
</html>
"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(page, encoding="utf-8")
    return dest


def html_newer_than_json(html_path: Path, json_path: Path) -> bool:
    """HTML mtime 是否新于 JSON。"""

    if not html_path.is_file() or not json_path.is_file():
        return False
    return html_path.stat().st_mtime > json_path.stat().st_mtime + 0.01
