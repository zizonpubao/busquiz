// 문제팩 파일(busquiz-<책>.json) 불러오기 + 검증
import * as db from "./db.js";

export function validate(pack) {
  if (!pack || pack.format !== 1) throw new Error("BusQuiz 문제팩 파일이 아닙니다 (format 1이 아님).");
  if (!pack.book || !Array.isArray(pack.questions) || !pack.questions.length) throw new Error("문항이 없습니다.");
  if (!Array.isArray(pack.sets)) throw new Error("세트 목록이 없습니다.");
  for (const q of pack.questions) {
    if (!q.id || !q.stem || !Array.isArray(q.choices) || q.choices.length < 2) throw new Error(`문항 형식 오류: ${q.id || "?"}`);
    q.book = pack.book;
  }
  return pack;
}

export async function importFile(file, onProgress = () => {}) {
  onProgress("파일 읽는 중…");
  const text = await file.text();
  onProgress("문항 확인 중…");
  const pack = validate(JSON.parse(text));
  onProgress(`${pack.name} ${pack.questions.length}문항 저장 중…`);
  await db.replaceBook(pack);
  return { book: pack.book, name: pack.name, count: pack.questions.length, version: pack.version };
}
