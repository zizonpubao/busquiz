// BusQuiz 화면 흐름: 홈 → 고르기 → 문제 → 결과 / 모의고사 / 통계 / 설정
import * as db from "./db.js";
import * as pack from "./pack.js";
import * as md from "./md.js";
import * as quiz from "./quiz.js";
import * as exam from "./exam.js";
import * as stats from "./stats.js";
import { el, esc, setTitle, render, bottom, toast, sheet, closeSheets, zoomImage, confirm, CIRC, circ, fmtTime } from "./ui.js";

const stack = [];                       // 뒤로 가기용 화면 스택
let tick = null;                        // 모의고사 타이머(화면을 떠나면 항상 멈춘다)
function go(fn, ...args) { clearInterval(tick); stack.push([fn, args]); return fn(...args); }
function back() { clearInterval(tick); stack.pop(); const top = stack[stack.length - 1]; closeSheets(); return top ? top[0](...top[1]) : home(); }
function reset(fn, ...args) { clearInterval(tick); stack.length = 0; return go(fn, ...args); }
document.querySelector("#back").onclick = back;
document.querySelector("#menu").onclick = () => {
  const s = sheet(`<div class="list">
    <button class="item" data-go="home"><span class="name">🏠 홈</span></button>
    <button class="item" data-go="stats"><span class="name">📊 진도·정답률</span></button>
    <button class="item" data-go="settings"><span class="name">⚙️ 문제팩·백업·설정</span></button></div>`);
  s.querySelectorAll("[data-go]").forEach((b) => b.onclick = () => { s.remove(); ({ home: () => reset(home), stats: () => go(statsScreen), settings: () => go(settings) })[b.dataset.go](); });
};

// ---------- 공통 ----------
const picked = { books: [] };
async function loadImages(q) {
  const names = [...(q.stem_images || []), ...(q.explanation_images || []), ...q.choices.map((c) => c.image).filter(Boolean)];
  const out = {};
  for (const n of names) { const r = await db.get("images", n); if (r) out[n] = r.data; }
  return out;
}
function tags(q, reveal) {
  const t = [];
  const k = quiz.answerKind(q); if (k) t.push(`<span class="tag ${k.cls}">${k.label}</span>`);
  if (reveal && Array.isArray(q.answer)) t.push(`<span class="tag ok">복수 정답 ${circ(q.answer)}</span>`);
  if (q.flags?.includes("answer_conflict") && q.answer != null) t.push(`<span class="tag bad">책 정답과 클로드 풀이 다름</span>`);
  if (q.inferred_fields?.length) t.push(`<span class="tag warn">추정 보완</span>`);
  if (q.flags?.includes("low_confidence")) t.push(`<span class="tag warn">일부 글자 판독 불가</span>`);
  if (q.claude_note?.key_concept?.startsWith("[확신 낮음")) t.push(`<span class="tag warn">클로드 확신 낮음</span>`);
  if (q.duplicate_of) t.push(`<span class="tag">같은 문제: ${esc(q.duplicate_of)}</span>`);
  return t.join("");
}
function passageHtml(p) {
  if (!p) return "";
  const lines = p.split("\n");
  const title = /^[〈<\[]/.test(lines[0]) ? lines.shift() : null;
  return `<div class="passage">${title ? `<div class="ptitle">${esc(title)}</div>` : ""}${md.text(lines.join("\n"))}</div>`;
}
function figsHtml(names, imgs) {
  const have = (names || []).filter((n) => imgs[n]);
  return have.length ? `<div class="figs">${have.map((n) => `<img src="${imgs[n]}" alt="" data-zoom>`).join("")}</div>` : "";
}
function questionHtml(q, imgs, state) {           // state: {pick, reveal, examMode}
  const a = quiz.effectiveAnswer(q);
  const aset = new Set(Array.isArray(a) ? a : (a ? [a] : []));
  const choices = q.choices.map((c, i) => {
    const n = i + 1; let cls = "choice";
    if (state.reveal) { if (aset.has(n)) cls += " correct"; else if (state.pick === n) cls += " wrong"; else cls += " dim"; }
    else if (state.pick === n) cls += " picked";
    return `<button class="${cls}" data-n="${n}"><span class="lab">${esc(c.label || CIRC[i])}</span><span class="ctext">${c.text != null ? md.text(c.text) : ""}${c.image && imgs[c.image] ? `<img src="${imgs[c.image]}" alt="">` : ""}</span></button>`;
  }).join("");
  const head = [q.set, `${q.number}번`, q.subject, q.part, q.exam_source, q.difficulty ? `난이도 ${q.difficulty}` : null].filter(Boolean).map(esc).join(" · ");
  return `<div class="qhead">${head}</div><div class="qhead">${state.examMode ? "" : tags(q, state.reveal)}</div>
    <p class="stem">${md.text(q.stem)}</p>${passageHtml(q.passage)}
    ${q.code?.text ? md.codeBlock(q.code.text, q.code.lang) : ""}${q.table_md ? md.markdown(q.table_md) : ""}
    ${figsHtml(q.stem_images, imgs)}<div class="choices">${choices}</div>`;
}
function explanationHtml(q, imgs, tab) {
  const n = q.claude_note || {};
  const book = q.book_explanation ? `<div class="expl">${md.markdown(q.book_explanation)}${figsHtml(q.explanation_images, imgs)}</div>`
    : `<p class="muted">이 문항에는 책 해설이 없습니다${q.answer == null ? " (책 정답·해설 사진이 없는 회차)" : ""}.</p>`;
  const wow = Object.entries(n.why_others_wrong || {}).sort().map(([k, v]) => `<li><span class="lab">${CIRC[k - 1] || k}</span>${md.text(v)}</li>`).join("");
  const claude = `<div class="expl">
    ${n.key_concept ? `<div class="note-sec"><b>핵심</b>${md.text(n.key_concept)}</div>` : ""}
    ${wow ? `<div class="note-sec"><b>다른 보기</b><ul class="wow">${wow}</ul></div>` : ""}
    ${n.trace ? `<div class="note-sec"><b>따라가기</b><pre class="code"><code>${esc(n.trace)}</code></pre></div>` : ""}
    ${n.extend ? `<div class="note-sec"><b>공기업 전공에서는</b>${md.text(n.extend)}</div>` : ""}
    ${n.conflict ? `<div class="badge-note"><b>책 정답과 다른 이유</b><br>${md.text(n.conflict)}</div>` : ""}
    ${q.claude_answer != null ? `<p class="muted small">클로드 풀이: ${circ(q.claude_answer)}</p>` : ""}</div>`;
  return `<div class="tabs"><button class="chip ${tab === "book" ? "on" : ""}" data-tab="book">책 해설</button><button class="chip ${tab === "claude" ? "on" : ""}" data-tab="claude">클로드 보충</button></div>
    <div id="expl">${tab === "book" ? book : claude}</div>`;
}
function wireImages(root) { root.querySelectorAll("img[data-zoom]").forEach((im) => im.onclick = () => zoomImage(im.src)); }

// ---------- 홈 ----------
async function home() {
  const packs = await db.all("packs");
  setTitle("BusQuiz", "", { back: false }); bottom(null);
  if (!packs.length) {
    render(`<div class="card"><h2>문제팩이 없습니다</h2><p class="muted">아이폰 "파일" 앱(iCloud Drive)에 넣어 둔 <code>busquiz-gs.json</code>, <code>busquiz-jc.json</code>을 불러오세요. 책마다 하나씩, 한 번만 하면 됩니다.</p>
      <button class="btn primary" id="imp">문제팩 불러오기</button></div>`);
    document.querySelector("#imp").onclick = importPack; return;
  }
  if (!picked.books.length) picked.books = packs.map((p) => p.book);
  const s = await stats.summary();
  const last = await quiz.lastSession(); const lastEx = await exam.lastExam();
  const bookChips = packs.map((p) => `<button class="chip ${picked.books.includes(p.book) ? "on" : ""}" data-book="${p.book}">${esc(p.name)}</button>`).join("");
  render(`
    ${last ? `<button class="item" id="resume"><span class="name">▶ 이어풀기: ${esc(last.title)}</span><span class="meta">${last.idx + 1}/${last.qids.length}</span></button>` : ""}
    ${lastEx ? `<button class="item" id="resumeExam"><span class="name">⏱ 이어서: ${esc(lastEx.title)}</span><span class="meta">${Object.keys(lastEx.answers).length}/100 답함</span></button>` : ""}
    <div class="card"><h2>책 (여러 권 섞기 가능)</h2><div class="chips">${bookChips}</div></div>
    <div class="card"><h2>풀기</h2><div class="list">
      <button class="item" data-mode="set"><span class="name">세트별로 풀기</span><span class="meta">PART·회차</span></button>
      <button class="item" data-mode="subject"><span class="name">과목별로 풀기</span><span class="meta">고른 책 섞어서</span></button>
      <button class="item" data-mode="random"><span class="name">랜덤 N문제</span></button>
      <button class="item" data-mode="wrong"><span class="name">오답만 풀기</span><span class="meta">${s.wrong}개</span></button>
      <button class="item" data-mode="confused"><span class="name">헷갈림 표시한 것만</span><span class="meta">${s.confused}개</span></button>
      <button class="item" data-mode="unsolved"><span class="name">아직 안 푼 문제</span><span class="meta">${s.total - s.solved}개</span></button>
    </div></div>
    ${packs.some((p) => p.book === "jc") ? `<div class="card"><h2>정보처리기사 모의고사</h2><p class="muted small">회차 100문항, 150분 타이머(끌 수 있음). 끝나면 과목별 점수와 과락·합격 표시.</p><button class="btn" id="examBtn">회차 고르기</button></div>` : ""}
    <div class="card"><div class="row"><div class="grow"><b>진도</b> <span class="muted">${s.solved}/${s.total} 문항 · 정답률 ${s.attempts ? Math.round(100 * s.correct / s.attempts) : 0}%</span></div><button class="chip small" id="statsBtn">자세히</button></div>
      <div class="bar" style="margin-top:8px"><i style="width:${s.total ? 100 * s.solved / s.total : 0}%"></i></div></div>`);
  const m = document.querySelector("#main");
  m.querySelectorAll("[data-book]").forEach((b) => b.onclick = () => {
    const k = b.dataset.book; picked.books = picked.books.includes(k) ? picked.books.filter((x) => x !== k) : [...picked.books, k];
    if (!picked.books.length) picked.books = [k]; home();
  });
  m.querySelectorAll("[data-mode]").forEach((b) => b.onclick = () => startMode(b.dataset.mode));
  m.querySelector("#resume")?.addEventListener("click", () => go(question, last));
  m.querySelector("#resumeExam")?.addEventListener("click", () => go(examQuestion, lastEx));
  m.querySelector("#examBtn")?.addEventListener("click", () => go(pickExam));
  m.querySelector("#statsBtn").onclick = () => go(statsScreen);
}

async function startMode(mode) {
  const books = picked.books;
  if (mode === "set") return go(pickSet, books);
  if (mode === "subject") return go(pickSubject, books);
  if (mode === "random") {
    const s = sheet(`<h2 style="margin:0 0 10px">몇 문제?</h2><div class="btn-row">${[10, 20, 50].map((n) => `<button class="btn" data-n="${n}">${n}</button>`).join("")}</div>`);
    s.querySelectorAll("[data-n]").forEach((b) => b.onclick = async () => { s.remove(); await begin("random", { books, random: true, limit: +b.dataset.n }, `랜덤 ${b.dataset.n}문제`); });
    return;
  }
  const title = { wrong: "오답 다시 풀기", confused: "헷갈림 표시한 문제", unsolved: "아직 안 푼 문제" }[mode];
  await begin(mode, { books, only: mode, random: mode !== "unsolved" }, title);
}
async function begin(mode, filter, title) {
  const s = await quiz.newSession(mode, filter, title);
  if (!s) return toast("해당하는 문제가 없습니다");
  go(question, s);
}

async function pickSet(books) {
  setTitle("세트 고르기"); bottom(null);
  const packs = (await db.all("packs")).filter((p) => books.includes(p.book));
  const s = await stats.summary();
  let html = "";
  for (const p of packs) {
    const b = s.books.find((x) => x.book === p.book);
    html += `<div class="card"><h2>${esc(p.name)}</h2><div class="list">` + p.sets.map((st) => {
      const t = b?.sets[st.id] || { solved: 0, total: st.count, correct: 0, attempts: 0 };
      return `<button class="item" data-set="${st.id}" data-name="${esc(st.name)}"><div class="grow"><div class="name">${esc(st.name)}</div><div class="bar" style="margin-top:6px"><i style="width:${100 * t.solved / t.total}%"></i></div></div><span class="meta">${t.solved}/${t.total}${t.attempts ? ` · ${Math.round(100 * t.correct / t.attempts)}%` : ""}</span></button>`;
    }).join("") + "</div></div>";
  }
  render(html).querySelectorAll("[data-set]").forEach((b) => b.onclick = () => begin("set", { books, sets: [b.dataset.set] }, b.dataset.name));
}
async function pickSubject(books) {
  setTitle("과목 고르기", books.join("+")); bottom(null);
  const s = await stats.summary();
  const counts = {};
  for (const b of books) for (const q of await db.allBy("questions", "book", b)) counts[q.subject] = (counts[q.subject] || 0) + 1;
  const order = quiz.subjectOrder(await db.all("packs"), Object.keys(counts));
  render(`<div class="card"><div class="list">${order.map((x) => {
    const t = s.subjects[x]; return `<button class="item" data-subj="${x}"><div class="grow"><div class="name">${x}</div><div class="bar" style="margin-top:6px"><i style="width:${t.total ? 100 * t.solved / t.total : 0}%"></i></div></div><span class="meta">${counts[x]}문항</span></button>`;
  }).join("")}</div></div>
  <div class="card"><label class="row"><input type="checkbox" id="rnd" checked> 순서 섞기</label></div>`);
  document.querySelectorAll("[data-subj]").forEach((b) => b.onclick = () => begin("subject", { books, subjects: [b.dataset.subj], random: document.querySelector("#rnd").checked }, b.dataset.subj));
}

// ---------- 문제 풀기 ----------
async function question(s) {
  if (s.idx >= s.qids.length) return go(result, s);
  const q = await db.get("questions", s.qids[s.idx]);
  if (!q) { s.idx++; return question(s); }
  const imgs = await loadImages(q);
  const prog = await quiz.getProgress(q.id);
  const saved = s.answers[q.id];
  const state = { pick: saved?.pick ?? null, reveal: saved != null, examMode: false };
  setTitle(s.title, `${s.idx + 1} / ${s.qids.length} ▸`, { onSub: () => go(quizGrid, s) });
  let tab = "book";
  const draw = () => {
    const m = render(`<div class="card">${questionHtml(q, imgs, state)}
      ${state.reveal ? `<div class="verdict ${saved.ok === true ? "ok" : saved.ok === false ? "bad" : ""}">${saved.ok === true ? "정답!" : saved.ok === false ? `틀림 — 정답 ${circ(quiz.effectiveAnswer(q))}` : "채점 제외 문항"}</div>${explanationHtml(q, imgs, tab)}` : ""}</div>`);
    wireImages(m);
    if (!state.reveal) m.querySelectorAll(".choice").forEach((b) => b.onclick = async () => {
      const pick = +b.dataset.n; const r = await quiz.record(q, pick, s.mode);
      s.answers[q.id] = { pick, ok: r.ok }; await quiz.saveSession(s);
      state.pick = pick; state.reveal = true; question(s);
    });
    m.querySelectorAll("[data-tab]").forEach((b) => b.onclick = () => { tab = b.dataset.tab; draw(); });
    bar();
  };
  const bar = () => bottom([
    { label: (prog?.confused ? "★ 헷갈림" : "☆ 헷갈림"), cls: "ghost side", side: true, onClick: async () => { const on = await quiz.toggleConfused(q); toast(on ? "헷갈림 표시" : "표시 해제"); question(s); } },
    { label: "‹", cls: "ghost side", side: true, disabled: s.idx === 0, onClick: async () => { s.idx--; await quiz.saveSession(s); question(s); } },
    { label: state.reveal ? (s.idx + 1 < s.qids.length ? "다음 →" : "결과 보기") : "건너뛰기", cls: state.reveal ? "primary" : "ghost",
      onClick: async () => { s.idx++; await quiz.saveSession(s); question(s); } },
  ]);
  draw();
}
// 풀기 모드 문항 현황 화면: 문항마다 한 줄(번호 · 발문 앞부분 · 맞음/틀림/건너뜀), 누르면 그 문항으로
const snip = (q, n = 60) => { const t = (q?.stem || "").replace(/\s+/g, " ").trim(); return t.length > n ? t.slice(0, n) + "…" : t; };
async function quizGrid(s) {
  const vals = Object.values(s.answers);
  const ok = vals.filter((a) => a.ok === true).length, bad = vals.filter((a) => a.ok === false).length;
  const skipped = s.qids.slice(0, s.idx).filter((id) => !s.answers[id]).length;
  setTitle("문항 현황", `${s.idx + 1} / ${s.qids.length}`);
  bottom([{ label: "문제로 돌아가기", cls: "primary", onClick: back }]);
  const qs = await Promise.all(s.qids.map((id) => db.get("questions", id)));
  const rows = s.qids.map((id, i) => {
    const a = s.answers[id];
    const st = a ? (a.ok === true ? ["ok", "맞음"] : a.ok === false ? ["bad", `틀림 · 정답 ${circ(quiz.effectiveAnswer(qs[i]))}`] : ["done", "채점 제외"]) : (i < s.idx ? ["skip", "건너뜀"] : ["", ""]);
    return `<button class="item qrow ${st[0]} ${i === s.idx ? "cur" : ""}" data-i="${i}"><span class="num">${i + 1}</span><span class="grow snip">${esc(snip(qs[i]))}</span><span class="st">${st[1]}</span></button>`;
  }).join("");
  const m = render(`<div class="card"><h2 style="margin:0 0 8px">${esc(s.title)}</h2>
      <div class="row small" style="flex-wrap:wrap;gap:6px 14px"><span><i class="dot ok"></i> 맞음 ${ok}</span><span><i class="dot bad"></i> 틀림 ${bad}</span><span><i class="dot skip"></i> 건너뜀 ${skipped}</span><span><i class="dot"></i> 남음 ${s.qids.length - vals.length}</span></div>
      ${bad ? `<button class="btn ghost" id="gridWrong" style="margin-top:12px">틀린 ${bad}문항만 다시 풀기</button>` : ""}</div>
    <div class="list">${rows}</div>`);
  m.querySelector(".qrow.cur")?.scrollIntoView({ block: "center" });
  m.querySelectorAll("[data-i]").forEach((b) => b.onclick = async () => { s.idx = +b.dataset.i; await quiz.saveSession(s); back(); });
  m.querySelector("#gridWrong")?.addEventListener("click", async () => {
    const ids = Object.entries(s.answers).filter(([, a]) => a.ok === false).map(([id]) => id);
    const n = { id: "s" + Date.now(), mode: "wrong", filter: {}, title: s.title + " 오답", qids: ids, idx: 0, answers: {}, startedAt: Date.now(), updatedAt: Date.now(), done: false };
    await db.put("sessions", n); await db.setMeta("lastSession", n.id); reset(question, n);
  });
}
async function result(s) {
  s.done = true; await quiz.saveSession(s);
  const vals = Object.values(s.answers); const ok = vals.filter((a) => a.ok === true).length, bad = vals.filter((a) => a.ok === false).length;
  setTitle("결과", s.title); bottom([{ label: "홈으로", cls: "primary", onClick: () => reset(home) }]);
  render(`<div class="card" style="text-align:center"><div class="score">${ok} / ${ok + bad}</div><p class="muted">맞음 ${ok} · 틀림 ${bad} · 건너뜀 ${s.qids.length - vals.length}</p></div>
    ${bad ? `<div class="card"><button class="btn" id="redo">틀린 ${bad}문제 바로 다시 풀기</button></div>` : ""}`);
  document.querySelector("#redo")?.addEventListener("click", async () => {
    const ids = Object.entries(s.answers).filter(([, a]) => a.ok === false).map(([id]) => id);
    const n = { id: "s" + Date.now(), mode: "wrong", filter: {}, title: "방금 틀린 문제", qids: ids, idx: 0, answers: {}, startedAt: Date.now(), updatedAt: Date.now(), done: false };
    await db.put("sessions", n); await db.setMeta("lastSession", n.id); reset(question, n);
  });
}

// ---------- 모의고사 ----------
async function pickExam() {
  setTitle("모의고사 회차"); bottom(null);
  const pk = await db.get("packs", "jc"); const s = await stats.summary();
  render(`<div class="card"><label class="row"><input type="checkbox" id="timer" checked> 150분 타이머 켜기</label></div>
    <div class="card"><div class="list">${pk.sets.filter((x) => x.exam).map((x) => `<button class="item" data-set="${x.id}"><span class="name">${esc(x.name)}</span><span class="meta">${s.books.find((b) => b.book === "jc")?.sets[x.id]?.solved || 0}/100 푼 적 있음</span></button>`).join("")}</div></div>`);
  document.querySelectorAll("[data-set]").forEach((b) => b.onclick = async () => {
    const e = await exam.newExam(b.dataset.set, document.querySelector("#timer").checked);
    if (!e) return toast("100문항이 아닌 회차입니다"); stack.length = 0; stack.push([home, []]); go(examQuestion, e);
  });
}
async function examQuestion(s) {
  clearInterval(tick);
  const q = await db.get("questions", s.qids[s.idx]); const imgs = await loadImages(q);
  const state = { pick: s.answers[q.id] ?? null, reveal: false, examMode: true };
  const left = () => exam.EXAM_SEC - s.elapsed;
  setTitle(s.title, `${s.idx + 1}/100 ▸`, { onSub: () => go(examGrid, s) });
  const m = render(`<div class="card">${s.useTimer ? `<div class="row"><span class="timer" id="tm">${fmtTime(left())}</span><span class="muted small">남음 · 답함 ${Object.keys(s.answers).length}/100</span></div>` : `<div class="muted small">답함 ${Object.keys(s.answers).length}/100</div>`}${questionHtml(q, imgs, state)}</div>`);
  wireImages(m);
  m.querySelectorAll(".choice").forEach((b) => b.onclick = async () => { s.answers[q.id] = +b.dataset.n; await db.put("sessions", s); examQuestion(s); });
  if (s.useTimer) {
    let lastT = Date.now();
    tick = setInterval(async () => {
      s.elapsed += Math.round((Date.now() - lastT) / 1000); lastT = Date.now();
      const t = document.querySelector("#tm"); if (t) { t.textContent = fmtTime(Math.max(0, left())); t.classList.toggle("low", left() < 600); }
      if (s.elapsed % 15 === 0) await db.put("sessions", s);
      if (left() <= 0) { clearInterval(tick); toast("시간 종료"); finishExam(s); }
    }, 1000);
  }
  bottom([
    { label: "‹", cls: "ghost side", side: true, disabled: s.idx === 0, onClick: () => { s.idx--; examQuestion(s); } },
    { label: "문항표", cls: "ghost", onClick: () => go(examGrid, s) },
    { label: s.idx === 99 ? "제출" : "›", cls: s.idx === 99 ? "primary" : "primary side", side: s.idx !== 99, onClick: async () => { if (s.idx === 99) { if (await confirm("답안을 제출할까요? 안 푼 문항은 틀린 것으로 칩니다.", "제출")) finishExam(s); } else { s.idx++; await db.put("sessions", s); examQuestion(s); } } },
  ]);
}
async function examGrid(s) {
  setTitle("문항표", `답함 ${Object.keys(s.answers).length} / 100`);
  bottom([{ label: "문제로 돌아가기", cls: "primary", onClick: back }, { label: "제출", cls: "ghost side", side: true, onClick: async () => { if (await confirm("답안을 제출할까요? 안 푼 문항은 틀린 것으로 칩니다.", "제출")) { stack.pop(); finishExam(s); } } }]);
  const qs = await Promise.all(s.qids.map((id) => db.get("questions", id)));
  const m = render(`<div class="card"><h2 style="margin:0">${esc(s.title)}</h2><p class="muted small" style="margin:4px 0 0">누르면 그 문항으로. 채점은 제출 뒤에.</p></div>
    <div class="list">${s.qids.map((id, i) => { const a = s.answers[id]; return `<button class="item qrow ${a != null ? "done" : ""} ${i === s.idx ? "cur" : ""}" data-i="${i}"><span class="num">${i + 1}</span><span class="grow snip">${esc(snip(qs[i]))}</span><span class="st">${a != null ? circ(a) : ""}</span></button>`; }).join("")}</div>`);
  m.querySelector(".qrow.cur")?.scrollIntoView({ block: "center" });
  m.querySelectorAll("[data-i]").forEach((b) => b.onclick = async () => { s.idx = +b.dataset.i; await db.put("sessions", s); back(); });
}
async function finishExam(s) {
  clearInterval(tick);
  const g = await exam.grade(s); await exam.commit(s);
  setTitle("모의고사 결과", s.title); bottom([{ label: "홈으로", cls: "primary", onClick: () => reset(home) }]);
  render(`<div class="card" style="text-align:center"><div class="score ${g.pass ? "" : ""}" style="color:var(--${g.pass ? "ok" : "bad"})">${g.pass ? "합격" : "불합격"}</div>
    <p class="muted">평균 ${g.avg.toFixed(1)}점 · 맞은 문항 ${g.total}/100 · ${s.useTimer ? `걸린 시간 ${fmtTime(s.elapsed)}` : "타이머 끔"}</p></div>
    <div class="card">${g.subjects.map((x) => `<div class="stat-row"><span>${esc(x.name)}${x.fail ? ' <span class="tag bad">과락</span>' : ""}</span><span class="n">${x.score}점 (${x.correct}/20${x.unanswered ? `, 안 푼 ${x.unanswered}` : ""})</span></div>`).join("")}</div>
    <div class="card"><button class="btn" id="review">틀린 문항 해설 보기</button></div>`);
  document.querySelector("#review").onclick = async () => {
    const ids = [];
    for (const id of s.qids) { const q = await db.get("questions", id); const pick = s.answers[id]; const ok = pick == null ? false : quiz.isCorrect(q, pick); if (ok !== true) ids.push(id); }
    if (!ids.length) return toast("틀린 문항이 없습니다");
    const n = { id: "s" + Date.now(), mode: "review", filter: {}, title: "모의고사 오답 복습", qids: ids, idx: 0, answers: {}, startedAt: Date.now(), updatedAt: Date.now(), done: false };
    await db.put("sessions", n); await db.setMeta("lastSession", n.id); reset(question, n);
  };
}

// ---------- 통계·설정 ----------
async function statsScreen() {
  setTitle("진도·정답률"); bottom(null);
  const s = await stats.summary();
  const row = (name, t) => `<div class="stat-row"><span>${esc(name)}</span><span class="n">${t.solved}/${t.total}${t.attempts ? ` · ${Math.round(100 * t.correct / t.attempts)}%` : ""}${t.wrong ? ` · 오답 ${t.wrong}` : ""}</span></div>`;
  render(`<div class="card"><h2>책별</h2>${s.books.map((b) => row(b.name, b)).join("")}</div>
    <div class="card"><h2>과목별 (책 합산)</h2>${quiz.subjectOrder(await db.all("packs"), Object.keys(s.subjects).filter((x) => s.subjects[x].total)).map((x) => row(x, s.subjects[x])).join("")}</div>
    ${s.books.map((b) => `<div class="card"><h2>${esc(b.name)} 세트별</h2>${Object.values(b.sets).map((t) => row(t.name, t)).join("")}</div>`).join("")}`);
}
async function settings() {
  setTitle("문제팩·백업·설정"); bottom(null);
  const packs = await db.all("packs"); const theme = await db.getMeta("theme", "auto"); const fs = await db.getMeta("fs", 17);
  render(`<div class="card"><h2>문제팩</h2><div class="list">${packs.map((p) => `<div class="item"><div class="grow"><div class="name">${esc(p.name)}</div><div class="muted small">${p.count}문항 · 팩 ${esc(p.version?.slice(0, 10) || "")}</div></div><button class="chip small danger" data-rm="${p.book}">삭제</button></div>`).join("")}</div>
      <p class="muted small">같은 책을 다시 불러오면 문제 내용만 바뀌고 학습 기록은 그대로 남습니다.</p><button class="btn primary" id="imp">문제팩 불러오기</button></div>
    <div class="card"><h2>학습 기록 백업</h2><div class="btn-row"><button class="btn" id="exp">내보내기(JSON)</button><button class="btn" id="impb">불러오기</button></div></div>
    <div class="card"><h2>화면</h2><div class="row"><span class="grow">테마</span><div class="chips">${["auto", "light", "dark"].map((t) => `<button class="chip small ${theme === t ? "on" : ""}" data-theme="${t}">${{ auto: "자동", light: "밝게", dark: "어둡게" }[t]}</button>`).join("")}</div></div>
      <div class="row" style="margin-top:10px"><span class="grow">글자 크기</span><div class="chips">${[15, 17, 19, 21].map((n) => `<button class="chip small ${fs === n ? "on" : ""}" data-fs="${n}">${n}</button>`).join("")}</div></div></div>
    <div class="card"><button class="btn ghost danger" id="wipe">학습 기록 전부 지우기</button></div>
    <p class="muted small">BusQuiz v1 · 문제 데이터는 이 기기 안에만 저장됩니다.</p>`);
  const m = document.querySelector("#main");
  m.querySelector("#imp").onclick = importPack;
  m.querySelectorAll("[data-rm]").forEach((b) => b.onclick = async () => { if (await confirm("이 책의 문제를 지울까요? 학습 기록은 남습니다.", "삭제")) { await db.removeBook(b.dataset.rm); toast("지웠습니다"); settings(); } });
  m.querySelector("#exp").onclick = async () => {
    const data = JSON.stringify(await stats.exportBackup());
    const blob = new Blob([data], { type: "application/json" }); const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `busquiz-backup-${new Date().toISOString().slice(0, 10)}.json`; a.click();
  };
  m.querySelector("#impb").onclick = () => pickFile(async (f) => { const n = await stats.importBackup(JSON.parse(await f.text())); toast(`기록 ${n}건 합쳤습니다`); });
  m.querySelectorAll("[data-theme]").forEach((b) => b.onclick = async () => { await db.setMeta("theme", b.dataset.theme); applyPrefs(); settings(); });
  m.querySelectorAll("[data-fs]").forEach((b) => b.onclick = async () => { await db.setMeta("fs", +b.dataset.fs); applyPrefs(); settings(); });
  m.querySelector("#wipe").onclick = async () => { if (await confirm("학습 기록(정답률·오답·헷갈림)을 모두 지울까요? 문제는 남습니다.", "지우기")) { for (const p of await db.all("progress")) await db.del("progress", p.qid); for (const s of await db.all("sessions")) await db.del("sessions", s.id); toast("지웠습니다"); } };
}
function pickFile(cb) {
  const inp = document.createElement("input"); inp.type = "file"; inp.accept = ".json,application/json";
  inp.onchange = async () => { const f = inp.files[0]; if (!f) return; try { await cb(f); } catch (e) { toast("실패: " + e.message, 4000); } };
  inp.click();
}
function importPack() {
  pickFile(async (f) => {
    const sh = sheet(`<p id="pmsg">파일 읽는 중…</p>`);
    try {
      const r = await pack.importFile(f, (m) => { const p = document.querySelector("#pmsg"); if (p) p.textContent = m; });
      sh.remove(); toast(`${r.name} ${r.count}문항 불러왔습니다`); picked.books = []; reset(home);
    } catch (e) { sh.remove(); throw e; }
  });
}
async function applyPrefs() {
  const theme = await db.getMeta("theme", "auto"); const fs = await db.getMeta("fs", 17);
  if (theme === "auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.dataset.theme = theme;
  document.documentElement.style.setProperty("--fs", fs + "px");
}

// ---------- 시작 ----------
(async () => {
  try { if (navigator.storage?.persist) await navigator.storage.persist(); } catch {}
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("./sw.js").catch(() => {});
  await applyPrefs();
  reset(home);
})();
