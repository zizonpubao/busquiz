"""검수 조각(data/review/_parts/*.md)을 data/review.md 하나로 합친다.

- 등급별("꼭 확인" / "확인 권장" / "참고")로 모아 세트 순으로 정렬
- 머리의 "본 문항" 수와 "이상 없음" 수를 더해 요약
- 책 사이 중복(data/review/_dupes_cross.txt)을 "참고"에 붙인다
사용: python tools/qa_merge.py
"""
import json, re, sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
PARTS = ROOT / "data" / "review" / "_parts"
LEVELS = ["꼭 확인", "확인 권장", "참고"]


def main():
    plan = {p["name"]: p for p in json.loads((ROOT / "data" / "qa_plan.json").read_text(encoding="utf-8"))}
    items = defaultdict(list)
    seen, clean, done = 0, 0, []
    for name in plan:
        f = PARTS / f"{name}.md"
        if not f.exists():
            continue
        done.append(name)
        seen += len(plan[name]["must"]) + len(plan[name]["sample"])  # 계획 기준(전수 전환분은 제외)
        level = None
        for line in f.read_text(encoding="utf-8").splitlines():
            h = re.match(r"^#+\s*(.*)", line)
            if h:
                t = h.group(1)
                level = next((l for l in LEVELS if t.startswith(l)), None)
                m = re.search(r"이상 없음[^0-9]*(\d+)", t)
                if m:
                    clean += int(m.group(1))
                continue
            # 문항 id가 있는 줄만 (조각마다 "없음" 같은 빈 항목은 뺀다)
            if level and line.lstrip().startswith("-") and re.search(r"[a-z]{2}-s\d\d-q\d{3}", line):
                items[level].append(line.rstrip())
    missing = [n for n in plan if n not in done]
    out = ["# 검수 결과 (5단계 qa-verifier, 자동 합침: tools/qa_merge.py)", "",
           f"조각 {len(done)}/{len(plan)} 끝" + (f" — 아직: {', '.join(missing)}" if missing else ""),
           f"본 문항 약 {seen} · 이상 없음 약 {clean} · 꼭 확인 {len(items['꼭 확인'])} · 확인 권장 {len(items['확인 권장'])} · 참고 {len(items['참고'])}", ""]
    for lv in LEVELS:
        out += [f"## {lv}" + (" (답이 바뀔 수 있음)" if lv == "꼭 확인" else ""), ""]
        out += sorted(items[lv], key=lambda s: re.sub(r"^\W+", "", s)) or ["- 없음"]
        out.append("")
    dup = ROOT / "data" / "review" / "_dupes_cross.txt"
    if dup.exists():
        out += ["## 책 사이 중복 (find_dupes, 유사도 0.85 이상)", ""] + \
               [f"- {l.strip()}" for l in dup.read_text(encoding="utf-8").splitlines()[1:] if l.strip()] + [""]
    (ROOT / "data" / "review.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out[2:4]))


if __name__ == "__main__":
    main()
