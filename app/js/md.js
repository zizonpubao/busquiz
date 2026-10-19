// 아주 작은 마크다운 렌더러. 책 해설(표·``` 코드·굵게·목록)과 본문(<u>만 허용) 용.
// HTML은 전부 이스케이프하고 <u>…</u>와 표 칸 안의 <br>만 살린다.
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export function inline(s) {
  let h = esc(s);
  h = h.replace(/&lt;u&gt;([\s\S]*?)&lt;\/u&gt;/g, "<u>$1</u>");   // 밑줄만 허용
  h = h.replace(/\\\*/g, "&#42;");                                   // \* 이스케이프
  h = h.replace(/`([^`\n]+)`/g, (_, c) => `<code>${c}</code>`);
  h = h.replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>");
  // 위첨자: 2^10, 2^-5, 2^(n-1), 2^n → <sup>. 공백이 있는 a ^ b(XOR)는 건드리지 않는다
  h = h.replace(/([\w)\]])\^(-?\d+(?:[.,]\d+)?|\([^()\s]{1,12}\)|[a-zA-Z](?![a-zA-Z]))/g, "$1<sup>$2</sup>");
  return h;
}

// 본문(발문·보기·지문): 줄바꿈 유지, 밑줄만
export function text(s) {
  if (s == null) return "";
  return inline(s).replace(/\n/g, "<br>");
}

// 코드 블록: 줄 번호 + 가로 스크롤 (gs-s07-q105처럼 "라인 N"을 가리키는 문제용)
export function codeBlock(code, lang = "") {
  const lines = String(code).replace(/\s+$/, "").split("\n");
  const w = String(lines.length).length;
  const body = lines.map((l, i) => `<span class="ln">${String(i + 1).padStart(w, " ")}</span>${esc(l) || " "}`).join("\n");
  return `<pre class="code" data-lang="${esc(lang)}"><code>${body}</code></pre>`;
}

function table(lines) {
  const rows = lines.filter((l) => !/^\s*\|?\s*:?-{2,}/.test(l)).map((l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim()));
  if (!rows.length) return "";
  const cell = (c) => inline(c).replace(/&lt;br&gt;/g, "<br>");
  const head = `<tr>${rows[0].map((c) => `<th>${cell(c)}</th>`).join("")}</tr>`;
  const body = rows.slice(1).map((r) => `<tr>${r.map((c) => `<td>${cell(c)}</td>`).join("")}</tr>`).join("");
  return `<div class="tbl"><table><thead>${head}</thead><tbody>${body}</tbody></table></div>`;
}

export function markdown(src) {
  if (!src) return "";
  const out = [];
  const lines = String(src).split("\n");
  let i = 0;
  while (i < lines.length) {
    const l = lines[i];
    if (/^```/.test(l)) {                                   // 코드 블록
      const lang = l.slice(3).trim(); const buf = []; i++;
      while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
      i++; out.push(codeBlock(buf.join("\n"), lang)); continue;
    }
    if (/^\s*\|/.test(l)) {                                 // 표
      const buf = []; while (i < lines.length && /^\s*\|/.test(lines[i])) buf.push(lines[i++]);
      out.push(table(buf)); continue;
    }
    if (/^\s*([-•*]|\d+\.)\s+/.test(l)) {                   // 목록
      const buf = []; while (i < lines.length && /^\s*([-•*]|\d+\.)\s+/.test(lines[i])) buf.push(lines[i++]);
      out.push(`<ul>${buf.map((b) => `<li>${inline(b.replace(/^\s*([-•*]|\d+\.)\s+/, ""))}</li>`).join("")}</ul>`); continue;
    }
    if (/^#{1,4}\s/.test(l)) { out.push(`<p class="h">${inline(l.replace(/^#+\s*/, ""))}</p>`); i++; continue; }
    if (!l.trim()) { i++; continue; }
    const buf = [l]; i++;
    while (i < lines.length && lines[i].trim() && !/^(```|\s*\||#{1,4}\s|\s*([-•*]|\d+\.)\s+)/.test(lines[i])) buf.push(lines[i++]);
    out.push(`<p>${buf.map(inline).join("<br>")}</p>`);
  }
  return out.join("");
}
