"""[판독불가] 추정 보완(CLAUDE.md 절대 규칙 3의 예외)을 모으고 반영한다.

사용:
  python tools/fills.py list     채울 대상 → data/questions/_fills/targets.json (조각별 문항 id + 정답 단계 힌트)
  python tools/fills.py apply    data/questions/_fills/<조각>.json 결과를 세트 파일에 반영
  python tools/fills.py adopt    책 정답을 못 읽은 문항(해설 포함 구역)에 클로드 풀이를 정답으로 ("클로드 추론")

결과 파일 형식 (에이전트가 씀):
  [{"id", "field", "occurrence", "fill", "basis", "confidence": "high"|"low", "note"}]
  field: stem / passage / table_md / code.text / choices.N (N은 1부터) / exam_source / book_explanation
  occurrence: 그 필드 안에서 몇 번째 [판독불가]인지 (1부터)
- high만 채운다. 채우면 inferred 플래그 + inferred 기록, 문항에 [판독불가]가 하나도 안 남으면 low_confidence를 뗀다
- 여러 번 돌려도 같다(이미 채운 자리는 [판독불가]가 없어 건너뜀)

순서: merge_questions → normalize → merge_answers → normalize → fills apply → fills adopt
"""
import json, re, sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
QDIR = ROOT / "data" / "questions"
FDIR = QDIR / "_fills"
MARK = "[판독불가]"
CHUNK = 25


def load_sets():
    return {f: json.loads(f.read_text(encoding="utf-8")) for f in sorted(QDIR.glob("*.json"))}


def get_field(q, field):
    if field.startswith("choices."):
        ch = q["choices"][int(field.split(".")[1]) - 1]
        return ch.get("text"), lambda v: ch.__setitem__("text", v)
    if field == "code.text":
        return (q.get("code") or {}).get("text"), lambda v: q["code"].__setitem__("text", v)
    return q.get(field), lambda v: q.__setitem__(field, v)


def cmd_list():
    FDIR.mkdir(exist_ok=True)
    issues = defaultdict(list)
    for line in (ROOT / "data" / "answer_issues.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"- ((?:gs|jc)-s\d\d-q\d{3}): (.*)", line)
        if m:
            issues[m.group(1)].append(m.group(2))
    by_set = defaultdict(list)
    for f, qs in load_sets().items():
        for q in qs:
            if MARK in json.dumps(q, ensure_ascii=False):
                by_set[q["id"][:6]].append(q["id"])
    chunks = []
    for sid, ids in sorted(by_set.items()):
        for i in range(0, len(ids), CHUNK):
            part = ids[i:i + CHUNK]
            chunks.append({"name": f"{sid}-{part[0][-4:]}-{part[-1][-4:]}", "set": sid, "ids": part,
                           "hints": {x: issues[x] for x in part if issues[x]}})
    (FDIR / "targets.json").write_text(json.dumps(chunks, ensure_ascii=False, indent=1), encoding="utf-8")
    for c in chunks:
        print(c["name"], len(c["ids"]))
    print("문항", sum(len(c["ids"]) for c in chunks), "조각", len(chunks))


def cmd_apply():
    results = defaultdict(list)
    for f in FDIR.glob("*.json"):
        if f.name == "targets.json":
            continue
        for r in json.loads(f.read_text(encoding="utf-8")):
            results[r["id"]].append(r)
    filled = skipped = low = 0
    for f, qs in load_sets().items():
        changed = False
        for q in qs:
            # 같은 필드 안에서는 뒤쪽 자리부터 바꿔야 앞쪽 번호가 안 밀린다
            for r in sorted(results.get(q["id"], []), key=lambda r: (r["field"], -r["occurrence"])):
                if r.get("confidence") != "high":
                    low += 1
                    continue
                text, setter = get_field(q, r["field"])
                parts = (text or "").split(MARK)
                n = r["occurrence"]
                if len(parts) <= n:
                    skipped += 1
                    continue
                after = MARK.join(parts[:n]) + r["fill"] + MARK.join(parts[n:])
                setter(after)
                q.setdefault("inferred", []).append({"field": r["field"], "before": text, "after": after,
                                                     "basis": r["basis"]})
                if "inferred" not in q["flags"]:
                    q["flags"].append("inferred")
                filled += 1
                changed = True
            if "inferred" in q["flags"] and MARK not in json.dumps({k: v for k, v in q.items() if k != "inferred"},
                                                                   ensure_ascii=False):
                if "low_confidence" in q["flags"]:
                    q["flags"].remove("low_confidence")
                    changed = True
        if changed:
            f.write_text(json.dumps(qs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"채움 {filled}곳, 낮은 확신이라 안 채움 {low}곳, 이미 채워져 건너뜀 {skipped}곳")


def cmd_adopt():
    decisions = json.loads((ROOT / "data" / "decisions.json").read_text(encoding="utf-8")).get("questions", {})
    n = 0
    for f, qs in load_sets().items():
        changed = False
        for q in qs:
            only_q = q["book"] == "jc" and int(q["id"][4:6]) >= 6
            if only_q or q["id"] in decisions or "missing_answer" not in q["flags"] or q.get("claude_answer") is None:
                continue
            q["answer"] = q["claude_answer"]
            q["answer_source"] = "클로드 추론"
            q["flags"].remove("missing_answer")
            n += 1
            changed = True
        if changed:
            f.write_text(json.dumps(qs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"클로드 추론으로 정답 채움: {n}문항")


if __name__ == "__main__":
    {"list": cmd_list, "apply": cmd_apply, "adopt": cmd_adopt}.get(
        (sys.argv[1:] or [""])[0], lambda: print(__doc__))()
