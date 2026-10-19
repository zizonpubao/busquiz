"""5단계 검수(qa-verifier) 조각 계획을 만든다 → data/qa_plan.json

검수 대상 고르기 (qa-verifier.md 규칙):
- 전부: 플래그 달린 문항(inferred, low_confidence, crop_check, answer_conflict), 코드·표·그림 있는 문항
- 나머지: 세트당 30% 무작위 (seed 고정)
조각 = 세트 묶음 하나. 결과는 data/review/_parts/<조각 이름>.md 에 쓰고 tools/qa_merge.py가 합친다.

사용: python tools/qa_plan.py
"""
import json, random, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
GROUPS = [["gs-s01"], ["gs-s02"], ["gs-s03"], ["gs-s04", "gs-s08"], ["gs-s05", "gs-s06"], ["gs-s07"],
          ["jc-s01", "jc-s02"], ["jc-s03", "jc-s04"], ["jc-s05", "jc-s06"], ["jc-s07", "jc-s08"],
          ["jc-s09", "jc-s10"], ["jc-s11", "jc-s12"], ["jc-s13", "jc-s14"], ["jc-s15"]]
FLAGS = {"inferred", "low_confidence", "crop_check", "answer_conflict"}


def must(q):
    return bool(set(q["flags"]) & FLAGS or q.get("code") or q.get("table_md") or q.get("stem_images")
                or any(c.get("image") for c in q["choices"]) or q.get("explanation_images"))


def main():
    rng = random.Random(20261018)
    plan = []
    for g in GROUPS:
        ids, sample, total = [], [], 0
        for sid in g:
            qs = json.loads((ROOT / "data" / "questions" / f"{sid}.json").read_text(encoding="utf-8"))
            total += len(qs)
            m = [q["id"] for q in qs if must(q)]
            rest = [q["id"] for q in qs if not must(q)]
            k = max(1, round(len(qs) * 0.3) - len(m)) if len(m) < len(qs) * 0.3 else max(3, round(len(rest) * 0.1))
            s = sorted(rng.sample(rest, min(k, len(rest))))
            ids += m
            sample += s
        plan.append({"name": "+".join(g), "sets": g, "total": total, "must": sorted(ids), "sample": sample})
    (ROOT / "data" / "qa_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in plan:
        print(f"{p['name']:16} 문항 {p['total']:4}  필수 {len(p['must']):3}  표본 {len(p['sample']):3}")
    print("합계 필수", sum(len(p["must"]) for p in plan), "표본", sum(len(p["sample"]) for p in plan))


if __name__ == "__main__":
    main()
