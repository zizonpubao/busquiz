// 화면 조립 도우미: 제목·하단 바·시트·토스트·이미지 확대
const $ = (s) => document.querySelector(s);
export const main = () => $("#main");

export function el(html) {
  const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild;
}
export function esc(s) { return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }

export function setTitle(title, sub = "", { back = true, onSub = null } = {}) {
  $("#title").textContent = title; $("#subtitle").textContent = sub;
  $("#back").classList.toggle("hidden", !back);
  const st = $("#subtitle"); st.onclick = onSub; st.classList.toggle("link", !!onSub);
}

export function render(html) {
  const m = main(); m.innerHTML = html; window.scrollTo(0, 0); return m;
}

// 하단 고정 바: [{label, cls, onClick, side}] / 없으면 숨김
export function bottom(buttons) {
  const b = $("#bottom"); b.innerHTML = "";
  if (!buttons || !buttons.length) { b.classList.add("hidden"); return; }
  b.classList.remove("hidden");
  for (const x of buttons) {
    const btn = el(`<button class="btn ${x.cls || ""} ${x.side ? "side" : ""}">${x.label}</button>`);
    btn.onclick = x.onClick; if (x.disabled) btn.disabled = true; b.appendChild(btn);
  }
}

let toastT;
export function toast(msg, ms = 1800) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove("show"), ms);
}

export function sheet(html) {
  const s = el(`<div class="sheet"><div class="panel">${html}</div></div>`);
  s.addEventListener("click", (e) => { if (e.target === s) s.remove(); });
  $("#layer").appendChild(s); return s;
}
export function closeSheets() { $("#layer").innerHTML = ""; }

export function zoomImage(src) {
  const m = el(`<div class="modal"><div class="zoom"><img src="${src}" alt=""></div><button class="close" aria-label="닫기">✕</button></div>`);
  m.querySelector(".close").onclick = () => m.remove();
  m.querySelector(".zoom").addEventListener("click", (e) => { if (e.target.tagName !== "IMG") m.remove(); });
  $("#layer").appendChild(m);
}

export async function confirm(msg, okLabel = "확인") {
  return new Promise((res) => {
    const s = sheet(`<p style="margin:0 0 14px">${esc(msg)}</p><div class="btn-row"><button class="btn ghost" data-v="0">취소</button><button class="btn primary" data-v="1">${esc(okLabel)}</button></div>`);
    s.querySelectorAll("[data-v]").forEach((b) => b.onclick = () => { s.remove(); res(b.dataset.v === "1"); });
  });
}

export const CIRC = ["①", "②", "③", "④", "⑤", "⑥"];
export const circ = (a) => Array.isArray(a) ? a.map((x) => CIRC[x - 1]).join("·") : (a ? CIRC[a - 1] : "—");
export function fmtTime(sec) { const m = Math.floor(sec / 60), s = sec % 60; return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`; }
