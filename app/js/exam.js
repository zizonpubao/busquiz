// 정처기 회차 모의고사: 100문항, 150분(끌 수 있음), 끝나면 과목별 점수·과락·합격
import * as db from "./db.js";
import { effectiveAnswer } from "./quiz.js";

export const EXAM_SEC = 150 * 60;

export async function newExam(setId, useTimer) {
  const qs = (await db.allBy("questions", "book", "jc")).filter((q) => q.set_id === setId).sort((a, b) => a.number - b.number);
  if (qs.length !== 100) return null;
  const s = { id: "e" + Date.now(), mode: "exam", title: qs[0].set + " 모의고사", setId, qids: qs.map((q) => q.id), idx: 0, answers: {},
    startedAt: Date.now(), elapsed: 0, useTimer, done: false, updatedAt: Date.now() };
  await db.put("sessions", s); await db.setMeta("lastExam", s.id);
  return s;
}
export async function lastExam() {
  const id = await db.getMeta("lastExam"); if (!id) return null;
  const s = await db.get("sessions", id); return s && !s.done ? s : null;
}

// 과목: 1~20 → 1과목 … 81~100 → 5과목 (문항 번호 기준). 과목 이름은 문항 part에서
export async function grade(session) {
  const qs = await Promise.all(session.qids.map((id) => db.get("questions", id)));
  const subj = [];
  for (let i = 0; i < 5; i++) {
    const part = qs.slice(i * 20, i * 20 + 20);
    let correct = 0, unanswered = 0;
    for (const q of part) {
      const pick = session.answers[q.id];
      if (pick == null) { unanswered++; continue; }
      const a = effectiveAnswer(q);
      // 책에 "정답 없음"(출제 오류)인 문항은 실제 시험처럼 답을 적었으면 전원 정답 처리
      if (a == null || (Array.isArray(a) ? a.includes(pick) : a === pick)) correct++;
    }
    subj.push({ name: part[0]?.part || `${i + 1}과목`, correct, score: correct * 5, unanswered, fail: correct * 5 < 40 });
  }
  const total = subj.reduce((s, x) => s + x.score, 0);
  const avg = total / 5;
  return { subjects: subj, avg, pass: avg >= 60 && !subj.some((x) => x.fail), total: subj.reduce((s, x) => s + x.correct, 0) };
}

// 모의고사 결과도 학습 기록에 반영(오답 목록 포함)
export async function commit(session) {
  const qs = await Promise.all(session.qids.map((id) => db.get("questions", id)));
  const rows = [];
  for (const q of qs) {
    const pick = session.answers[q.id]; if (pick == null) continue;
    const a = effectiveAnswer(q); const ok = a == null ? null : (Array.isArray(a) ? a.includes(pick) : a === pick);
    const p = (await db.get("progress", q.id)) || { qid: q.id, book: q.book, attempts: 0, correct: 0, wrong: 0, streak: 0, inWrong: false, confused: false };
    p.attempts++; p.last = pick; p.lastAt = Date.now();
    if (ok === true) { p.correct++; p.streak++; } else if (ok === false) { p.wrong++; p.streak = 0; p.inWrong = true; }
    rows.push(p);
  }
  await db.putMany("progress", rows);
  session.done = true; session.finishedAt = Date.now(); await db.put("sessions", session);
}
