"""question-extractor 조각(data/questions/_parts/*.json)을 세트 파일로 합친다.

- 계획(data/extract_plan.json) 대비 진행 상황: 끝난 조각 / 남은 조각
- 조각마다 맡은 범위의 문항이 빠짐없이, 범위 밖 문항 없이 들어 있는지
- 세트 파일 data/questions/{세트 id}.json 은 그 세트의 조각이 전부 끝났을 때만 만든다
  (이미 정답·해설이 붙은 세트 파일이 있으면 덮어쓰지 않고 알린다)

합친 뒤에는 반드시 python tools/normalize_questions.py 를 돌린다 (다시 합치면 표기 정리가 풀린다).

사용: python tools/merge_questions.py            진행 상황 + 끝난 세트 합치기
      python tools/merge_questions.py --status   진행 상황만
"""
import json, sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
QDIR = ROOT / "data" / "questions"
PARTS = QDIR / "_parts"


def main():
    status_only = "--status" in sys.argv
    plan = json.loads((ROOT / "data" / "extract_plan.json").read_text(encoding="utf-8"))
    done, todo, problems = [], [], []
    by_set = defaultdict(list)
    for i, c in enumerate(plan):
        f = ROOT / c["out"]
        if not f.exists():
            todo.append(i)
            continue
        try:
            qs = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            problems.append(f"#{i} {f.name}: JSON 읽기 실패 {e}")
            todo.append(i)
            continue
        want = set(range(c["q_from"], c["q_to"] + 1))
        got = [q.get("number") for q in qs]
        missing = sorted(want - set(got))
        extra = sorted(set(got) - want)
        dup = sorted({n for n in got if got.count(n) > 1})
        if missing or extra or dup:
            problems.append(f"#{i} {f.name}: 빠짐 {missing} 범위 밖 {extra} 중복 {dup}")
        imgs = [im for q in qs for im in (q.get("stem_images") or []) + [ch.get("image") for ch in q.get("choices") or []] if im]
        lost = [im for im in imgs if not (ROOT / "data" / "assets" / im).is_file()]
        if lost:
            problems.append(f"#{i} {f.name}: 크롭 파일 없음 {lost[:5]}")
        done.append(i)
        by_set[c["set_id"]].append((c, qs))

    total = sum(c["count"] for c in plan)
    got_n = sum(plan[i]["count"] for i in done)
    print(f"조각 {len(done)}/{len(plan)} 끝, 문항 {got_n}/{total}")
    print(f"남은 조각: {todo}")
    for p in problems:
        print("  ⚠", p)
    if status_only:
        return

    for sid in sorted(by_set):
        chunks = [c for c in plan if c["set_id"] == sid]
        if len(by_set[sid]) < len(chunks):
            continue
        out = QDIR / f"{sid}.json"
        qs = sorted((q for _, part in by_set[sid] for q in part), key=lambda q: q["number"])
        if out.exists():
            old = json.loads(out.read_text(encoding="utf-8"))
            if any(q.get("answer_source") or q.get("claude_note") for q in old):
                print(f"  {sid}: 정답·해설이 붙은 세트 파일이 있어 덮어쓰지 않음")
                continue
        out.write_text(json.dumps(qs, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {sid}: {len(qs)}문항 → {out.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
