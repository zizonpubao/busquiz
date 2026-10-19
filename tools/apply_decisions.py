"""사용자 결정(data/decisions.json)과 그 규칙을 세트 파일에 반영한다. 파이프라인 맨 끝에 돌린다.

1. questions: 문항별 결정
   - answer / answer_source / claude_answer 가 있으면 그 값으로
   - no_answer: true → answer null + no_answer 플래그 (채점 제외)
   - choice_fix: {"보기번호": "고친 글"}
   - resolution: 기록만 (데이터는 그대로, 앱이 보여 줄 수 있음)
2. rules.same_question_answer: 정처기 문제만 구역(s06~s15) 문항이 같은 책 해설 포함 구역(s01~s05) 문항과
   발문·지문·코드·표·보기가 같으면 그 책 정답을 쓴다 (answer_source "같은 문제 책 정답", duplicate_of)
3. rules.subject_boundaries: subject가 "기타"인 문항만 키워드로 구체 과목에 옮긴다

순서: … → fills apply → fills adopt → apply_patch → apply_decisions
사용: python tools/apply_decisions.py
"""
import difflib, json, re, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
QDIR = ROOT / "data" / "questions"
SUBJECT_RULES = [
    ("데이터베이스", r"하둡|Hadoop|HDFS|Sqoop|맵리듀스|MapReduce|빅데이터|Big ?Data"),
    ("네트워크", r"RFID|NFC|IoT|사물인터넷|USN"),
    ("운영체제", r"가상화|하이퍼바이저|Hypervisor|도커|Docker|컨테이너"),
    ("정보보안", r"블록체인|Blockchain|DRM|디지털 저작권"),
    ("자료구조·알고리즘", r"색인 ?순차|ISAM|VSAM"),
]


def ws(s):
    # 공백과 대소문자 차이(Null/NULL)는 같은 문제로 본다
    return re.sub(r"\s+", "", s or "").casefold()


def full(q):
    return "|".join(ws(x) for x in (q["stem"], q.get("passage"), (q.get("code") or {}).get("text"), q.get("table_md")))


def as_list(a):
    return a if isinstance(a, list) else [a]


def main():
    dec = json.loads((ROOT / "data" / "decisions.json").read_text(encoding="utf-8"))
    files = {f: json.loads(f.read_text(encoding="utf-8")) for f in sorted(QDIR.glob("*.json"))}
    qs = [q for v in files.values() for q in v]
    log = {"결정": 0, "같은 문제": 0, "같은 문제·클로드와 다름": [], "과목": []}

    # 2. 같은 문제 책 정답 (해설 포함 구역 = jc s01~s05)
    known = [q for q in qs if q["book"] == "jc" and int(q["id"][4:6]) <= 5 and q.get("answer") is not None
             and q.get("answer_source") not in ("클로드 추론", None)]
    for q in qs:
        if not (q["book"] == "jc" and int(q["id"][4:6]) >= 6) or q["id"] in dec["questions"]:
            continue
        qc = [ws(c.get("text")) for c in q["choices"]]
        if any(not c for c in qc) or len(set(qc)) != len(qc):
            continue
        f, best = full(q), None
        for k in known:
            if sorted(ws(c.get("text")) for c in k["choices"]) != sorted(qc):
                continue
            r = difflib.SequenceMatcher(None, f, full(k)).ratio()
            if r >= 0.95 and (best is None or r > best[0]):
                best = (r, k)
        if not best:
            continue
        k = best[1]
        kc = [ws(c.get("text")) for c in k["choices"]]
        mapped = sorted({qc.index(kc[a - 1]) + 1 for a in as_list(k["answer"])})
        q["answer"] = mapped if len(mapped) > 1 else mapped[0]
        q["answer_source"] = "같은 문제 책 정답"
        q["duplicate_of"] = k["id"]
        q["flags"] = [x for x in q["flags"] if x != "missing_answer"]
        if sorted(as_list(q.get("claude_answer"))) != mapped:
            if "answer_conflict" not in q["flags"]:
                q["flags"].append("answer_conflict")
            q["claude_note"]["conflict"] = (f"같은 문제({k['id']})의 책 정답은 {mapped}이다. 클로드는 책 없이 풀어 "
                                            f"{q.get('claude_answer')}을 골랐으나 같은 책의 정답·해설을 따른다.")
            log["같은 문제·클로드와 다름"].append(q["id"])
        log["같은 문제"] += 1

    # 1. 문항별 결정
    byid = {q["id"]: q for q in qs}
    for qid, d in dec["questions"].items():
        q = byid.get(qid)
        if not q:
            continue
        for key in ("answer", "answer_source", "claude_answer", "duplicate_of"):
            if key in d:
                q[key] = d[key]
        if d.get("no_answer"):
            q["answer"] = None
            q["flags"] = [x for x in q["flags"] if x not in ("missing_answer", "answer_conflict")] + \
                         ([] if "no_answer" in q["flags"] else ["no_answer"])
        if "answer" in d and d["answer"] is not None:
            q["flags"] = [x for x in q["flags"] if x not in ("missing_answer", "no_answer")]
            if sorted(as_list(q["answer"])) == sorted(as_list(q.get("claude_answer"))):
                q["flags"] = [x for x in q["flags"] if x != "answer_conflict"]
        for n, text in (d.get("choice_fix") or {}).items():
            q["choices"][int(n) - 1]["text"] = text
        log["결정"] += 1

    # 3. 과목 경계 (기타 → 구체 과목만)
    for q in qs:
        if q["subject"] != "기타":
            continue
        t = q["stem"] + " " + (q.get("passage") or "")
        for subj, pat in SUBJECT_RULES:
            if re.search(pat, t):
                log["과목"].append(f"{q['id']}→{subj}")
                q["subject"] = subj
                break

    for f, v in files.items():
        f.write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"문항별 결정 {log['결정']}, 같은 문제 책 정답 {log['같은 문제']}"
          f" (클로드와 다름 {len(log['같은 문제·클로드와 다름'])}: {log['같은 문제·클로드와 다름']}), 과목 이동 {len(log['과목'])}")


if __name__ == "__main__":
    main()
