"""answer-explainer 조각(data/questions/_answers/*.json)을 세트 파일에 붙인다.

조각 하나 = data/extract_plan.json의 조각 하나(파일 이름 같음). 조각 안 항목:
  {"id", "answer", "answer_source", "book_explanation", "claude_answer", "claude_note",
   "answer_pages": [...], "flags_add": [...], "extract_issue": "본문 옮김이 이상해 보이면 한 줄" | null}
- 세트 파일의 문제 본문(stem·choices·code 등)은 건드리지 않는다
- flags는 기존 플래그 + flags_add (중복 없이)
- data/decisions.json의 questions 값이 마지막에 덮어쓴다 (사용자 확정)
- extract_issue는 data/answer_issues.md로 모은다

순서: merge_questions.py → normalize_questions.py → merge_answers.py → normalize_questions.py → fills.py apply → fills.py adopt → apply_patch.py → apply_decisions.py → apply_review.py
사용: python tools/merge_answers.py            진행 상황 + 붙이기 + 일치율
      python tools/merge_answers.py --status   진행 상황만
"""
import json, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
QDIR = ROOT / "data" / "questions"
ADIR = QDIR / "_answers"
KEYS = {"id", "answer", "answer_source", "book_explanation", "claude_answer", "claude_note",
        "answer_pages", "flags_add", "extract_issue"}


def main():
    status_only = "--status" in sys.argv
    plan = json.loads((ROOT / "data" / "extract_plan.json").read_text(encoding="utf-8"))
    decisions = json.loads((ROOT / "data" / "decisions.json").read_text(encoding="utf-8")).get("questions", {})
    done, todo, problems = [], [], []
    items = {}
    for i, c in enumerate(plan):
        f = ADIR / Path(c["out"]).name
        if not f.exists():
            todo.append(i)
            continue
        try:
            rows = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            problems.append(f"#{i} {f.name}: JSON 읽기 실패 {e}")
            todo.append(i)
            continue
        want = {f"{c['set_id']}-q{n:03d}" for n in range(c["q_from"], c["q_to"] + 1)}
        got = [r.get("id") for r in rows]
        missing, extra = sorted(want - set(got)), sorted(set(got) - want)
        dup = sorted({x for x in got if got.count(x) > 1})
        odd = sorted({k for r in rows for k in r} - KEYS)
        if missing or extra or dup or odd:
            problems.append(f"#{i} {f.name}: 빠짐 {missing[:8]} 범위 밖 {extra[:8]} 중복 {dup} 모르는 키 {odd}")
        done.append(i)
        for r in rows:
            items[r["id"]] = r

    total = sum(c["count"] for c in plan)
    print(f"정답 조각 {len(done)}/{len(plan)} 끝, 문항 {sum(plan[i]['count'] for i in done)}/{total}")
    print(f"남은 조각: {todo}")
    for p in problems:
        print("  ⚠", p)
    if status_only:
        return

    issues, stats = [], defaultdict(Counter)
    for f in sorted(QDIR.glob("*.json")):
        qs = json.loads(f.read_text(encoding="utf-8"))
        changed = False
        for q in qs:
            r = items.get(q["id"])
            if r:
                for k in ("answer", "answer_source", "book_explanation", "claude_answer", "claude_note"):
                    q[k] = r.get(k)
                q["source"]["answer_pages"] = r.get("answer_pages") or []
                q["flags"] = list(dict.fromkeys((q.get("flags") or []) + (r.get("flags_add") or [])))
                if r.get("extract_issue"):
                    issues.append(f"- {q['id']}: {r['extract_issue']}")
                changed = True
            d = decisions.get(q["id"])
            if d:
                for k, v in d.items():
                    if k in ("answer", "answer_source"):
                        q[k] = v
                q["flags"] = [x for x in q["flags"] if x not in ("missing_answer",)]
                changed = True
            if q.get("claude_answer") is None and q.get("answer") is None:
                continue
            s = stats[f.stem]
            if q.get("answer") is None:
                s["책 정답 없음"] += 1
            elif q.get("claude_answer") == q.get("answer"):
                s["일치"] += 1
            else:
                s["불일치"] += 1
        if changed:
            f.write_text(json.dumps(qs, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n세트별: 일치 / 불일치 / 책 정답 없음 (일치율)")
    tot = Counter()
    for sid, s in sorted(stats.items()):
        tot.update(s)
        n = s["일치"] + s["불일치"]
        print(f"  {sid}: {s['일치']} / {s['불일치']} / {s['책 정답 없음']}" + (f"  ({s['일치'] / n:.1%})" if n else ""))
    n = tot["일치"] + tot["불일치"]
    if n:
        print(f"  전체: {tot['일치']} / {tot['불일치']} / {tot['책 정답 없음']}  ({tot['일치'] / n:.1%})")
    (ROOT / "data" / "answer_issues.md").write_text(
        "# 정답 단계에서 발견한 본문 옮김 문제 (자동 생성: tools/merge_answers.py)\n\n" + ("\n".join(issues) or "없음") + "\n",
        encoding="utf-8")
    print(f"\ndata/answer_issues.md: {len(issues)}건")


if __name__ == "__main__":
    main()
