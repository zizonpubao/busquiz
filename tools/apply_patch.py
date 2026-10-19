"""재촬영본으로 다시 읽은 결과(data/questions/_patch/*.json)를 세트 파일에 반영한다.

패치 항목 (에이전트가 씀):
  {"id", "fields": {"stem": "고친 전체 글", "choices.3": "…", "code.text": "…", "book_explanation": "…", ...},
   "answer": 번호|[번호…]|null, "answer_source": "정답 표시"|"정답 줄"|null,
   "conflict": "책 정답이 claude_answer와 다를 때만 근거 2~3문장"|null, "note": "한 줄"}
- fields: 사진으로 다시 읽어 바뀐(또는 확인한) 필드의 **전체 글**. [판독불가]가 남으면 그대로 둔다
- 사진으로 확인된 필드의 inferred 기록은 지운다(이제 추정이 아니라 사진에서 읽음)
- answer가 있으면 책 정답으로 쓴다. claude_answer와 다르면 answer_conflict + claude_note.conflict
- 문항에 [판독불가]가 안 남으면 low_confidence, inferred 기록이 안 남으면 inferred 플래그를 뗀다

순서: … → fills.py apply → fills.py adopt → apply_patch.py
사용: python tools/apply_patch.py
"""
import json, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
QDIR = ROOT / "data" / "questions"
MARK = "[판독불가]"


def set_field(q, field, value):
    if field.startswith("choices."):
        q["choices"][int(field.split(".")[1]) - 1]["text"] = value
    elif field == "code.text":
        q["code"]["text"] = value
    else:
        q[field] = value


def main():
    patches = {}
    for f in sorted((QDIR / "_patch").glob("*.json")):
        for p in json.loads(f.read_text(encoding="utf-8")):
            patches[p["id"]] = p
    n_field = n_ans = n_conf = 0
    for f in sorted(QDIR.glob("*.json")):
        qs = json.loads(f.read_text(encoding="utf-8"))
        changed = False
        for q in qs:
            p = patches.get(q["id"])
            if not p:
                continue
            for field, value in (p.get("fields") or {}).items():
                set_field(q, field, value)
                if MARK not in value and q.get("inferred"):
                    q["inferred"] = [r for r in q["inferred"] if r["field"] != field]
                n_field += 1
            if p.get("explanation_images"):
                q["explanation_images"] = p["explanation_images"]
            if p.get("answer") is not None:
                q["answer"] = p["answer"]
                q["answer_source"] = p.get("answer_source") or "정답 표시"
                q["flags"] = [x for x in q["flags"] if x not in ("missing_answer",)]
                n_ans += 1
                if q.get("claude_answer") is not None and q["claude_answer"] != q["answer"]:
                    if "answer_conflict" not in q["flags"]:
                        q["flags"].append("answer_conflict")
                    q["claude_note"]["conflict"] = p.get("conflict") or "재촬영본에서 읽은 책 정답이 클로드 풀이와 다름"
                    n_conf += 1
            if not q.get("inferred"):
                q.pop("inferred", None)
                q["flags"] = [x for x in q["flags"] if x != "inferred"]
            if MARK not in json.dumps({k: v for k, v in q.items() if k != "inferred"}, ensure_ascii=False):
                q["flags"] = [x for x in q["flags"] if x != "low_confidence"]
            changed = True
        if changed:
            f.write_text(json.dumps(qs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"패치 문항 {len(patches)}, 필드 {n_field}곳, 정답 {n_ans}문항(새 충돌 {n_conf})")


if __name__ == "__main__":
    main()
