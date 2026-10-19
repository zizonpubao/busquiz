// 진도·정답률 집계와 학습 기록 백업
import * as db from "./db.js";
import { SUBJECTS } from "./quiz.js";

export async function summary() {
  const packs = await db.all("packs");
  const prog = new Map((await db.all("progress")).map((p) => [p.qid, p]));
  const out = { books: [], subjects: {}, wrong: 0, confused: 0, total: 0, solved: 0, correct: 0, attempts: 0 };
  for (const s of SUBJECTS) out.subjects[s] = { total: 0, solved: 0, correct: 0, attempts: 0, wrong: 0 };
  for (const pk of packs) {
    const qs = await db.allBy("questions", "book", pk.book);
    const b = { book: pk.book, name: pk.name, total: qs.length, solved: 0, correct: 0, attempts: 0, wrong: 0, sets: {} };
    for (const st of pk.sets) b.sets[st.id] = { name: st.name, total: st.count, solved: 0, correct: 0, attempts: 0, wrong: 0 };
    for (const q of qs) {
      const p = prog.get(q.id); const su = out.subjects[q.subject] || (out.subjects[q.subject] = { total: 0, solved: 0, correct: 0, attempts: 0, wrong: 0 });
      su.total++; out.total++;
      const st = b.sets[q.set_id];
      if (!p || !p.attempts) continue;
      for (const t of [b, su, out, st].filter(Boolean)) { t.solved++; t.correct += p.correct; t.attempts += p.attempts; if (p.inWrong) t.wrong++; }
    }
    out.books.push(b);
  }
  for (const p of prog.values()) { if (p.inWrong) out.wrong++; if (p.confused) out.confused++; }
  return out;
}

export async function exportBackup() {
  const progress = await db.all("progress");
  const sessions = (await db.all("sessions")).filter((s) => !s.done).slice(-5);
  return { app: "busquiz", format: 1, exportedAt: new Date().toISOString(), progress, sessions };
}

// 가져오기: 기록은 id 기준 합침(시도 수가 더 많은 쪽, 오답·헷갈림은 OR)
export async function importBackup(obj) {
  if (obj?.app !== "busquiz" || !Array.isArray(obj.progress)) throw new Error("BusQuiz 백업 파일이 아닙니다.");
  const cur = new Map((await db.all("progress")).map((p) => [p.qid, p]));
  const rows = [];
  for (const p of obj.progress) {
    const c = cur.get(p.qid);
    if (!c) { rows.push(p); continue; }
    const base = (p.attempts || 0) >= (c.attempts || 0) ? { ...p } : { ...c };
    base.inWrong = !!(p.inWrong || c.inWrong); base.confused = !!(p.confused || c.confused);
    rows.push(base);
  }
  await db.putMany("progress", rows);
  for (const s of obj.sessions || []) await db.put("sessions", s);
  return rows.length;
}
