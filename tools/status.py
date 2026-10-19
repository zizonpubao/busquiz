"""개발 현황 숫자를 모아 data/status.json 으로 쓴다 (읽기 전용: 다른 파일은 건드리지 않음).

사용:  python tools/status.py
결과에는 숫자·문항 id·단계 이름·결정 항목 제목만 담는다. 문제 본문·보기·해설·코드는 넣지 않는다(저작권).
"""
import json, re, subprocess, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
QDIR = DATA / "questions"
KST = timezone(timedelta(hours=9))
MARK = "[판독불가]"
BOOK_NAMES = {"gs": "공기업 전산직 전공", "jc": "정보처리기사 필기"}
BOOK_ANSWERS = ("정답 표시", "정답 줄", "정답표", "사용자 확정", "해설 문장")


def read(path):
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def load_questions():
    qs = []
    for f in sorted(QDIR.glob("*-s*.json")):
        qs += json.loads(f.read_text(encoding="utf-8"))
    return qs


def section(text, title_part):
    """'## ...title_part...' 제목 아래 다음 '## ' 전까지의 줄들."""
    out, on = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            on = title_part in line
            continue
        if on:
            out.append(line)
    return out


def _n(v):
    return len(v) if isinstance(v, (list, dict)) else (v or 0)


def qa_progress():
    """5단계 검수: data/qa_plan.json 조각 대비 data/review/_parts/<조각>.* 존재 수."""
    try:
        plan = json.loads(read(DATA / "qa_plan.json") or "[]")
    except Exception:
        plan = []
    parts = DATA / "review" / "_parts"
    have = {f.stem for f in parts.iterdir()} if parts.exists() else set()
    done = sum(1 for p in plan if p.get("name") in have)
    return {"pieces_total": len(plan), "pieces_done": done,
            "must": sum(_n(p.get("must")) for p in plan), "sample": sum(_n(p.get("sample")) for p in plan),
            "merged": (DATA / "review.md").exists()}


def stages(followups):
    heads = " ".join(l for l in followups.splitlines() if l.startswith("## "))
    done = lambda pat: re.search(pat, heads) is not None
    app = ROOT / "app"
    st = [
        ("0", "준비", (ROOT / "scans" / "prepared").exists()),
        ("1", "페이지 인덱스", (DATA / "pages.json").exists()),
        ("2", "샘플 검증", (DATA / "sample").exists()),
        ("3", "전체 추출", done(r"3단계 끝")),
        ("4", "정답·해설 연결", done(r"4단계 끝")),
        ("4.5", "[판독불가] 추정 보완", done(r"4\.5단계.*끝")),
        ("5", "검수(qa-verifier)", (DATA / "review.md").exists()),
        ("6", "PWA 앱 + 문제팩 빌드", (app / "index.html").exists() and (ROOT / "tools" / "build_pack.py").exists()),
        ("7", "배포", False),
    ]
    out, found = [], False
    for sid, name, ok in st:
        if ok:
            state = "done"
        elif sid == "5" and qa_progress()["pieces_total"] and (DATA / "review" / "_parts").exists():
            state, found = "doing", True
        elif sid == "5" and (DATA / "decisions_review.md").exists():
            state, found = "wait", True
        elif not found:
            state, found = "doing", True
        else:
            state = "todo"
        item = {"id": sid, "name": name, "state": state}
        if sid == "5" and state == "doing":
            q = qa_progress()
            item["detail"] = "_parts %d/%d" % (q["pieces_done"], q["pieces_total"])
        out.append(item)
    return out


def run_validate():
    try:
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "validate.py"), str(QDIR)],
                           capture_output=True, text=True, encoding="utf-8", timeout=120)
        txt = r.stdout
    except Exception:
        return {"errors": None, "warnings": None}
    e = re.search(r"오류\s*(\d+)건", txt)
    w = re.search(r"경고\s*(\d+)건", txt)
    return {"errors": int(e.group(1)) if e else None, "warnings": int(w.group(1)) if w else None}


def fills_progress(qs):
    fdir = QDIR / "_fills"
    try:
        targets = json.loads((fdir / "targets.json").read_text(encoding="utf-8"))
    except Exception:
        targets = []
    pieces, hi, lo = [], 0, 0
    for t in targets:
        p = fdir / (t["name"] + ".json")
        h = l = 0
        done = p.exists()
        if done:
            try:
                for r in json.loads(p.read_text(encoding="utf-8")):
                    if r.get("confidence") == "high":
                        h += 1
                    else:
                        l += 1
            except Exception:
                done = False
        hi, lo = hi + h, lo + l
        pieces.append({"name": t["name"], "ids": len(t.get("ids", [])), "done": done, "high": h, "low": l})
    inferred_recs = sum(len(q.get("inferred", [])) for q in qs)
    return {
        "pieces_total": len(pieces),
        "pieces_done": sum(1 for p in pieces if p["done"]),
        "high": hi, "low": lo,
        "pieces": pieces,
        "applied_questions": sum(1 for q in qs if "inferred" in q.get("flags", [])),
        "applied_spots": inferred_recs,
        "marker_spots_left": sum(json.dumps(q, ensure_ascii=False).count(MARK) for q in qs),
        "marker_body_questions_left": sum(1 for q in qs if MARK in json.dumps(
            [q.get("stem"), q.get("passage"), q.get("table_md"), (q.get("code") or {}).get("text"),
             [c.get("text") for c in q.get("choices", [])]], ensure_ascii=False)),
        "marker_questions_left": sum(1 for q in qs if MARK in json.dumps(q, ensure_ascii=False)),
    }


def reshoot():
    ext = read(DATA / "reshoot-extract.md")
    fin = read(DATA / "reshoot-final.md")
    tot = re.search(r"다시 찍을 사진\s*(\d+)장\s*\(gs\s*(\d+),\s*jc\s*(\d+)\)", ext)
    cut = sum(1 for l in section(ext, "본문 잘림") if l.startswith("- **"))
    num = sum(1 for l in section(ext, "정답 숫자 잘림") if l.startswith("- **"))
    gsm = re.search(r"공기업 전산직.*?—\s*(\d+)장", fin)
    jcm = re.search(r"정보처리기사.*?—\s*(\d+)장", fin)
    gs_f = int(gsm.group(1)) if gsm else None
    jc_f = int(jcm.group(1)) if jcm else None
    return {
        "extract_cut_photos": cut, "extract_answer_photos": num,
        "extract_total": int(tot.group(1)) if tot else None,
        "extract_gs": int(tot.group(2)) if tot else None,
        "extract_jc": int(tot.group(3)) if tot else None,
        "final_total": (gs_f or 0) + (jc_f or 0) if (gsm or jcm) else None,
        "final_gs": gs_f, "final_jc": jc_f,
    }


REPLACE_BASELINE = 16  # 2026-10-18 메인 세션이 알려 준 값: 이보다 늘면 재촬영 반영이 시작된 것


def count_replace(o):
    if isinstance(o, dict):
        return sum(1 if k == "replace_with" else count_replace(v) for k, v in o.items())
    if isinstance(o, list):
        return sum(count_replace(v) for v in o)
    return 0


def reshoot_apply(followups, final_total):
    try:
        n = count_replace(json.loads(read(DATA / "prep_overrides.json") or "{}"))
    except Exception:
        n = None
    if re.search(r"^## .*재촬영 반영.*끝", followups, re.M):
        state = "done"
    elif n is not None and n > REPLACE_BASELINE:
        state = "doing"
    else:
        state = "wait"
    return {"state": state, "replace_count": n, "baseline": REPLACE_BASELINE, "required": final_total}


GROUPS = {"A": "책 정답과 클로드 풀이가 다름", "C2": "출제 오류 의심", "C3": "클로드 확신 낮음(책 정답 없음)"}


def review_result():
    """data/review.md 맨 위 요약 숫자와 '꼭 확인' 문항 id만 읽는다(본문 문장은 옮기지 않음)."""
    t = read(DATA / "review.md")
    if not t:
        return None
    num = lambda pat: (lambda m: int(m.group(1)) if m else None)(re.search(pat, t))
    return {"checked": num(r"본 문항 약\s*(\d+)"), "clean": num(r"이상 없음 약\s*(\d+)"),
            "must": num(r"꼭 확인\s*(\d+)"), "recommend": num(r"확인 권장\s*(\d+)"), "note": num(r"참고\s*(\d+)"),
            "must_ids": sorted({m.group(1) for l in section(t, "꼭 확인") if l.startswith("- ")
                                for m in [re.match(r"- ([a-z]{2}-s\d+-q\d+)", l)] if m})}


def review_decisions():
    """data/decisions_review.md 의 '### 묶음-번호 — 문항id' 제목에서 문항 id만 모은다(본문은 읽지 않음)."""
    groups = {}
    for line in read(DATA / "decisions_review.md").splitlines():
        m = re.match(r"###\s+(?:(A)\d+|(C\d)-\d+)\s+—\s+([a-z]{2}-s\d+-q\d+)", line)
        if m:
            groups.setdefault(m.group(1) or m.group(2), []).append(m.group(3))
    try:
        rep = len(json.loads(read(DATA / "repeat_check.json") or "[]"))
    except Exception:
        rep = None
    return {"groups": [{"key": k, "label": GROUPS.get(k, k), "count": len(v), "ids": v} for k, v in groups.items()],
            "repeat_proposals": rep, "exists": (DATA / "decisions_review.md").exists()}


def clause(line):
    """결정 항목 제목: 첫 절만(콜론·여는 괄호 앞), 따옴표·백틱 속 내용 제외."""
    t = re.sub(r"[\"'`“”‘’].*?[\"'`“”‘’]", "", line.lstrip("- ").strip())
    t = re.split(r"[:：→]", t)[0]
    t = re.sub(r"\s*\([^)]*\)\s*$", "", t).strip(" ,")
    return t[:48]


def pending(followups, qs, decisions):
    items = [clause(l) for l in section(followups, "사용자에게 물을 것") if l.startswith("- ")]
    elsewhere = sum(1 for l in followups.splitlines()
                    if "사용자에게" in l and l.startswith("- ")
                    and not any(l.startswith("- " + i[:6]) for i in items))
    conflicts = sorted(q["id"] for q in qs if "answer_conflict" in q.get("flags", []))
    confirmed = sorted((decisions.get("questions") or {}).keys())
    return {"memo_items": items, "memo_other_count": elsewhere,
            "answer_conflicts": conflicts, "user_confirmed_ids": confirmed}


def main():
    qs = load_questions()
    followups = read(DATA / "extract_followups.md")
    try:
        decisions = json.loads(read(DATA / "decisions.json") or "{}")
    except Exception:
        decisions = {}

    books = {}
    for code in ("gs", "jc"):
        bq = [q for q in qs if q["book"] == code]
        sets = Counter(q["set"] for q in bq)
        # 세트 순서는 id 기준
        order = {}
        for q in bq:
            order.setdefault(q["id"].split("-")[1], q["set"])
        bk = [q for q in bq if q.get("answer") is not None and q.get("answer_source") in BOOK_ANSWERS]
        match = sum(1 for q in bk if q.get("answer") == q.get("claude_answer"))
        books[code] = {
            "name": BOOK_NAMES[code],
            "questions": len(bq),
            "sets": [{"key": k, "label": v, "count": sets[v]} for k, v in sorted(order.items())],
            "flags": dict(Counter(f for q in bq for f in q.get("flags", []))),
            "answer_source": dict(Counter(q.get("answer_source") or "책 정답 없음(문제만)" for q in bq)),
            "book_answer_n": len(bk), "match_n": match,
            "match_rate": round(match / len(bk) * 100, 1) if bk else None,
        }
    allbk = [q for q in qs if q.get("answer") is not None and q.get("answer_source") in BOOK_ANSWERS]
    allmatch = sum(1 for q in allbk if q.get("answer") == q.get("claude_answer"))

    out = {
        "generated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "total_questions": len(qs),
        "stages": stages(followups),
        "books": books,
        "flags": dict(Counter(f for q in qs for f in q.get("flags", []))),
        "answer_source": dict(Counter(q.get("answer_source") or "책 정답 없음(문제만)" for q in qs)),
        "match": {"book_answer_n": len(allbk), "match_n": allmatch,
                  "rate": round(allmatch / len(allbk) * 100, 1) if allbk else None,
                  "changed_after_book": 4},
        "validate": run_validate(),
        "fills": fills_progress(qs),
        "reshoot": reshoot(),
        "reshoot_apply": None,
        "pending": pending(followups, qs, decisions),
        "review_decisions": review_decisions(),
        "qa": qa_progress(),
        "review_result": review_result(),
    }
    out["reshoot_apply"] = reshoot_apply(followups, out["reshoot"]["final_total"])
    (DATA / "status.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    # 현황 페이지 db 문서용: {"status": ...} 한 겹 감싼 사본
    (DATA / "status_db.json").write_text(json.dumps({"status": out}, ensure_ascii=False), encoding="utf-8")
    print("data/status.json 갱신:", out["generated_at"], "문항", len(qs))


if __name__ == "__main__":
    main()
