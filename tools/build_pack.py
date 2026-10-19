"""책마다 문제팩 하나를 만든다 → packs/busquiz-<책코드>.json

팩 = 그 책의 모든 문항 + 문항이 쓰는 이미지(webp, base64 data URL). 앱(app/)이 아이폰 "파일" 앱에서 이 파일을 골라 불러온다.
팩 형식(format 1):
{
  "format": 1, "book": "gs", "name": "…", "version": "2026-10-19T…", "count": 1459,
  "sets": [{"id": "gs-s01", "name": "PART 01 전자계산기구조론", "count": 370, "exam": false}],
  "questions": [ … 문항 … ],      # 앱에 필요한 필드만 (source·inferred 원문 등은 뺌)
  "images": {"gs-s01-q013-fig1.webp": "data:image/webp;base64,…"}
}
문항 필드: id, book, set, set_id, number, subject, part, exam_source, difficulty, stem, passage, stem_images, code,
  table_md, choices, answer, answer_source, book_explanation, claude_note, claude_answer, flags, duplicate_of,
  explanation_images, inferred_fields(추정 보완된 필드 이름만), printed_page

사용: python tools/build_pack.py [gs jc …]   (생략하면 books.json의 모든 책)
"""
import base64, json, sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
QDIR, ASSETS, PACKS = ROOT / "data" / "questions", ROOT / "data" / "assets", ROOT / "packs"
KEEP = ["id", "book", "set", "number", "subject", "part", "exam_source", "difficulty", "stem", "passage", "stem_images",
        "code", "table_md", "choices", "answer", "answer_source", "book_explanation", "claude_note", "claude_answer",
        "flags", "duplicate_of", "explanation_images"]


def main():
    books = {b["code"]: b for b in json.loads((ROOT / "data" / "books.json").read_text(encoding="utf-8"))}
    codes = sys.argv[1:] or list(books)
    PACKS.mkdir(exist_ok=True)
    for code in codes:
        files = sorted(QDIR.glob(f"{code}-s*.json"))
        qs, sets, images = [], [], {}
        for f in files:
            rows = json.loads(f.read_text(encoding="utf-8"))
            if not rows:
                continue
            sid = f.stem
            sets.append({"id": sid, "name": rows[0]["set"], "count": len(rows),
                         "exam": code == "jc" and len(rows) == 100})
            for q in rows:
                out = {k: q.get(k) for k in KEEP if q.get(k) is not None or k in ("answer", "passage", "code", "table_md")}
                out["set_id"] = sid
                out["printed_page"] = q["source"].get("printed_page")
                if q.get("inferred"):
                    out["inferred_fields"] = sorted({r["field"] for r in q["inferred"]})
                qs.append(out)
                for name in (q.get("stem_images") or []) + (q.get("explanation_images") or []) + \
                            [c["image"] for c in q["choices"] if c.get("image")]:
                    p = ASSETS / name
                    if name not in images and p.is_file():
                        images[name] = "data:image/webp;base64," + base64.b64encode(p.read_bytes()).decode()
        pack = {"format": 1, "book": code, "name": books[code]["name"], "count": len(qs),
                "version": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                "sets": sets, "questions": qs, "images": images}
        dest = PACKS / f"busquiz-{code}.json"
        dest.write_text(json.dumps(pack, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{dest.relative_to(ROOT).as_posix()}: {len(qs)}문항, 세트 {len(sets)}, 이미지 {len(images)}장, "
              f"{dest.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
