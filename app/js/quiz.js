// 풀기 세션: 문항 고르기, 채점, 학습 기록(progress) 규칙
import * as db from "./db.js";

export const SUBJECTS = ["운영체제", "데이터베이스", "네트워크", "자료구조·알고리즘", "프로그래밍언어", "소프트웨어공학", "정보보안", "컴퓨터구조", "기타"];

// 정답 비교: 책 정답이 배열(복수 정답)이면 그중 하나를 고르면 맞음
export function isCorrect(q, pick) {
  const a = effectiveAnswer(q);
  if (a == null) return null;                      // 정답 없음(채점 제외)
  return Array.isArray(a) ? a.includes(pick) : a === pick;
}
// 책 정답이 없으면(문제만 구역) 클로드 풀이로 채점
export function effectiveAnswer(q) {
  if (q.flags?.includes("no_answer")) return null;
  if (q.answer != null) return q.answer;
  return q.claude_answer ?? null;
}
export function answerKind(q) {
  if (q.flags?.includes("no_answer")) return { label: "책 정답 없음 · 채점 제외", cls: "warn" };
  const s = q.answer_source;
  if (q.answer == null) return { label: "책 정답 없음 · 클로드 풀이로 채점", cls: "warn" };
  if (s === "클로드 추론") return { label: "책 정답 미확인(클로드 추론)", cls: "warn" };
  if (s === "같은 문제 책 정답") return { label: "같은 문제의 책 정답", cls: "ok" };
  if (s === "해설 문장") return { label: "정답은 책 해설 문장 근거", cls: "" };
  if (s === "사용자 확정") return { label: "사용자 확정 정답", cls: "ok" };
  return null;
}

export function shuffle(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
  return a;
}

// 조건에 맞는 문항 id 목록. filter = {books:[...], sets:[set_id], subjects:[...], only:"all"|"wrong"|"confused"|"unsolved", limit, random}
export async function selectIds(filter) {
  const books = filter.books?.length ? filter.books : (await db.all("packs")).map((p) => p.book);
  let qs = [];
  for (const b of books) qs = qs.concat(await db.allBy("questions", "book", b));
  if (filter.sets?.length) qs = qs.filter((q) => filter.sets.includes(q.set_id));
  if (filter.subjects?.length) qs = qs.filter((q) => filter.subjects.includes(q.subject));
  const prog = new Map((await db.all("progress")).map((p) => [p.qid, p]));
  if (filter.only === "wrong") qs = qs.filter((q) => prog.get(q.id)?.inWrong);
  if (filter.only === "confused") qs = qs.filter((q) => prog.get(q.id)?.confused);
  if (filter.only === "unsolved") qs = qs.filter((q) => !prog.get(q.id)?.attempts);
  qs.sort((a, b) => a.id < b.id ? -1 : 1);
  let ids = qs.map((q) => q.id);
  if (filter.random) ids = shuffle(ids);
  if (filter.limit) ids = ids.slice(0, filter.limit);
  return ids;
}

export async function newSession(mode, filter, title) {
  const qids = await selectIds(filter);
  if (!qids.length) return null;
  const s = { id: "s" + Date.now(), mode, filter, title, qids, idx: 0, answers: {}, startedAt: Date.now(), updatedAt: Date.now(), done: false };
  await db.put("sessions", s);
  await db.setMeta("lastSession", s.id);
  return s;
}
export async function saveSession(s) { s.updatedAt = Date.now(); return db.put("sessions", s); }
export async function lastSession() {
  const id = await db.getMeta("lastSession"); if (!id) return null;
  const s = await db.get("sessions", id); return s && !s.done ? s : null;
}

// 한 문항 채점 + 기록. 오답 규칙: 틀리면 오답 목록, 오답 모드에서 2번 연속 맞히면 빠짐
export async function record(q, pick, mode) {
  const ok = isCorrect(q, pick);
  const p = (await db.get("progress", q.id)) || { qid: q.id, book: q.book, attempts: 0, correct: 0, wrong: 0, streak: 0, inWrong: false, confused: false };
  p.attempts++; p.last = pick; p.lastAt = Date.now();
  if (ok === true) { p.correct++; p.streak++; if (p.inWrong && mode === "wrong" && p.streak >= 2) p.inWrong = false; }
  else if (ok === false) { p.wrong++; p.streak = 0; p.inWrong = true; }
  await db.put("progress", p);
  return { ok, progress: p };
}
export async function toggleConfused(q) {
  const p = (await db.get("progress", q.id)) || { qid: q.id, book: q.book, attempts: 0, correct: 0, wrong: 0, streak: 0, inWrong: false, confused: false };
  p.confused = !p.confused; await db.put("progress", p); return p.confused;
}
export async function getProgress(qid) { return db.get("progress", qid); }
