"""Sonnet이 푼 조각(문제만 구역, extract_plan 83~99번)에서 Opus가 다시 풀 문항을 고르고, 결과를 반영한다.

대상: key_concept이 "[확신 낮음"으로 시작하거나 코드(code)가 있는 문항.
재검 결과 파일 data/questions/_answers/_recheck/<세트>.json: [{"id", "opus_answer", "reason"}]
- 같으면: 그대로 두고 확신 낮음 표시만 "[확신 낮음 → Opus 재검 일치]"로 바꾼다
- 다르면: claude_answer를 Opus 답으로 바꾸고 key_concept 앞에
  "[확신 낮음: Sonnet ①·Opus ② 풀이가 갈림 — 사용자 확인 필요] "를 붙인다

사용: python tools/recheck.py list     대상 목록 → data/questions/_answers/_recheck/targets.json
      python tools/recheck.py apply    재검 결과를 _answers 조각 파일에 반영
"""
import json, re, sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
ADIR = ROOT / "data" / "questions" / "_answers"
RDIR = ADIR / "_recheck"
SONNET_CHUNKS = range(83, 100)
CIRCLED = "①②③④⑤"


def sonnet_files():
    plan = json.loads((ROOT / "data" / "extract_plan.json").read_text(encoding="utf-8"))
    return [ADIR / Path(plan[i]["out"]).name for i in SONNET_CHUNKS]


def targets():
    qs = {q["id"]: q for f in (ROOT / "data" / "questions").glob("*.json")
          for q in json.loads(f.read_text(encoding="utf-8"))}
    out = defaultdict(list)
    for f in sonnet_files():
        for r in json.loads(f.read_text(encoding="utf-8")):
            kc = (r.get("claude_note") or {}).get("key_concept") or ""
            why = "확신 낮음" if kc.startswith("[확신 낮음") else ("코드" if qs[r["id"]].get("code") else None)
            if why:
                out[r["id"][:6]].append({"id": r["id"], "why": why, "sonnet_answer": r.get("claude_answer")})
    return out


def label(a):
    return "·".join(CIRCLED[x - 1] for x in a) if isinstance(a, list) else (CIRCLED[a - 1] if a else "?")


def apply():
    results = {}
    for f in RDIR.glob("jc-s*.json"):
        for r in json.loads(f.read_text(encoding="utf-8")):
            results[r["id"]] = r
    same = diff = 0
    for f in sonnet_files():
        rows = json.loads(f.read_text(encoding="utf-8"))
        for r in rows:
            rc = results.get(r["id"])
            if not rc:
                continue
            note = r["claude_note"]
            kc = re.sub(r"^\[확신 낮음[^\]]*\]\s*", "", note.get("key_concept") or "")
            if rc["opus_answer"] == r["claude_answer"]:
                same += 1
                if (note.get("key_concept") or "").startswith("[확신 낮음"):
                    note["key_concept"] = "[확신 낮음 → Opus 재검 일치] " + kc
            else:
                diff += 1
                tag = f"[확신 낮음: Sonnet {label(r['claude_answer'])}·Opus {label(rc['opus_answer'])} 풀이가 갈림 — 사용자 확인 필요] "
                note["key_concept"] = tag + kc
                r["claude_answer"] = rc["opus_answer"]
        f.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"재검 반영: 일치 {same}, 갈림 {diff} (갈린 문항은 Opus 답으로 바꾸고 표시)")


def main():
    RDIR.mkdir(exist_ok=True)
    if sys.argv[1:] == ["list"]:
        t = targets()
        (RDIR / "targets.json").write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
        for sid, items in sorted(t.items()):
            print(sid, len(items), [i["id"][-4:] + ("*" if i["why"] == "확신 낮음" else "") for i in items])
        print("합계", sum(len(v) for v in t.values()), "(* = 확신 낮음, 나머지는 코드 문제)")
    elif sys.argv[1:] == ["apply"]:
        apply()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
