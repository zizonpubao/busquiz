// 아주 작은 마크다운 렌더러. 책 해설(표·``` 코드·굵게·목록)과 본문(<u>만 허용) 용.
// HTML은 전부 이스케이프하고 <u>…</u>와 표 칸 안의 <br>만 살린다.
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export function inline(s) {
  let h = esc(s);
  h = h.replace(/&lt;u&gt;([\s\S]*?)&lt;\/u&gt;/g, "<u>$1</u>");   // 밑줄만 허용
  h = h.replace(/\\\*/g, "&#42;");                                   // \* 이스케이프
  h = h.replace(/`([^`\n]+)`/g, (_, c) => `<code>${c}</code>`);
  h = h.replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>");
  // 수식: 인라인 코드(<code>) 안은 건드리지 않는다
  return h.split(/(<code>[\s\S]*?<\/code>)/).map((seg, i) => (i % 2 ? seg : formula(seg))).join("");
}

// 위첨자 x^2, 아래첨자 x_1. 공백이 있는 a ^ b(XOR)는 건드리지 않는다
const LATGRK = String.raw`\p{Script=Latin}\p{Script=Greek}ℓ`;                 // 수식 변수에 쓰는 글자: 라틴·그리스·ℓ
const SUB_TOKEN = String.raw`\(([^()]{1,14})\)|\d+|[\p{Script=Latin}ℓ∞]+\d*|\p{Script=Greek}+\d*|[Ⅰ-ⅿ]+|([\p{Script=Hangul}]+)`; // _(x=L/4) | _1 | _max | _Ⅱ | _강
const SUP_RE = /([\p{L}\p{N})\]])\^(-?\d+(?:[.,]\d+)?|\([^()\s]{1,12}\)|[\p{Script=Latin}\p{Script=Greek}ℓ](?![\p{Script=Latin}\p{Script=Greek}ℓ]))/gu;
const SUB_RE = new RegExp(String.raw`([${LATGRK}\p{M}0-9]+|[)\]|∫])_(${SUB_TOKEN})`, "gu");
const LEFT_SUB_RE = /(^|[^\p{L}\p{N}_])_(\d+)(?=\p{L}\p{M}*_)/gu;
const JOSA ="은는이가을를의와과로에도만";                                        // 아래첨자 한글 뒤에 붙은 조사 떼기용

// snake_case(int_arr, num_digits, MAX_QUEUE_SIZE)가 망가지지 않도록, 밑이 수식 기호처럼 생길 때만 첨자로 바꾼다
function subOk(base, sub, before, after, grouped) {
  if (before === "_" || after === "_") return false;
  if (/^[)\]|∫]$/.test(base)) return sub.length <= 14;                      // (…)_m, […]_0, |M|_max, ∫_0
  const core = (base.match(new RegExp(String.raw`[${LATGRK}\p{M}]+$`, "u")) || [""])[0].replace(/\p{M}/gu, ""); // 밑 끝의 글자 묶음 (1.5σ → σ, V̇ → V)
  if (!core) return false;
  if (/^[가-힣]+$/.test(sub)) return sub.length <= 8 && (core.length === 1 || /[\p{Script=Greek}]/u.test(core));  // σ_강, h_팽창밸브출구 (VIEW_이름 같은 낱말은 제외)
  if (sub.length > 14) return false;
  if (/log$/.test(core)) return /^(\d+|[A-Za-z])$/.test(sub);              // log_2, nlog_2
  if (core === "kg") return sub === "f";                                    // kg_f
  if (sub.length > 6 && !grouped) return false;                            // _(x=0.75L)처럼 괄호로 묶은 건 길어도 됨
  if (/[\p{Script=Greek}ℓ]/u.test(core)) return true;                  // πd_1, νσ_x (그리스 문자가 낀 곱은 코드 낱말이 아님)
  if (core.length === 1) return true;                                       // σ_max, P_1, c_p
  if (/^[A-Z]{3,}$/.test(core) && /^[A-Z]{2,}$/.test(sub)) return false;    // ARRAY_SIZE, CHK_AGE
  if (core.length <= 3 && /^(\d+|[A-Za-z])$/.test(sub)) return true;        // mc_p, ma_x, cmH_2O
  return !/[a-z]{2}/.test(core.replace(/[A-Z]/g, ""));                      // GI_p, ΣM_B, Fe_3C, NPSH_a (낱말 int_arr·student_id는 제외)
}

function subPass(h) {
  return h.replace(SUB_RE, (m, base, tok, paren, hangul, off, str) => {
    let sub = paren ?? tok, tail = "";
    if (hangul && hangul.length >= 3 && JOSA.includes(hangul.slice(-1))) { sub = hangul.slice(0, -1); tail = hangul.slice(-1); }
    else if (/^[A-Za-z]{2,}$/.test(sub) && str[off + m.length] === "_" && (/^\p{L}\p{M}*$/u.test(base) || /\p{Script=Greek}/u.test(base))) { tail = sub.slice(-1); sub = sub.slice(0, -1); }  // A_iE_i → A_i E_i (뒤 글자는 다음 변수)
    return subOk(base, sub, str[off - 1], tail || str[off + m.length], paren != null) ? `${base}<sub>${sub}</sub>${tail}` : m;
  });
}

function formula(h) {
  h = h.replace(SUP_RE, "$1<sup>$2</sup>");
  h = h.replace(LEFT_SUB_RE, "$1<sub>$2</sub>");                             // 열역학 _1Q_2 → ₁Q₂
  return subPass(subPass(h));                                                // 두 번: A_iE_i의 뒤쪽 E_i까지
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
