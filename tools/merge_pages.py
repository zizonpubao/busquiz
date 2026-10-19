"""page-indexer 결과(data/pages/*.json)를 합쳐 data/pages.json을 만들고 요약을 출력한다.

검사: 모든 쪽 이미지가 정확히 한 번씩 들어 있는지, 세트별 문항 번호 빈 곳,
정처기 회차별 100문항 여부. 재촬영 추천은 원본 사진 이름으로 바꿔 보여준다.
사용: python tools/merge_pages.py
"""
import json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
PARTS = ROOT / "data" / "pages"
PREPARED = ROOT / "scans" / "prepared"

# 정처기 책은 두 구역이 있고 구역마다 회차 번호를 01부터 다시 매긴다.
# 회차 첫 쪽이 범위 밖이라 "최신 기출문제 NN회"로만 적힌 쪽을 시행 연도·회차로 바꾼다.
JC_SECTION_SPLIT = "jc-p0114"  # 이 쪽('따로 보는' 구역 표지·목차) 앞은 해설 포함 구역
JC_ROUNDS = {
    "with_explanation": {1: "2020년 4회", 2: "2021년 1회", 3: "2021년 2회", 4: "2021년 3회", 5: "2022년 1회"},
    "questions_only": {1: "2022년 2회", 2: "2022년 3회", 3: "2023년 1회", 4: "2023년 2회", 5: "2023년 3회",
                       6: "2024년 1회", 7: "2024년 2회", 8: "2024년 3회", 9: "2025년 1회", 10: "2025년 2회"},
}


def normalize_jc(r):
    section = "with_explanation" if r["file"] < JC_SECTION_SPLIT else "questions_only"
    if r["file"] == JC_SECTION_SPLIT:
        section = "questions_only"
    r["section"] = section
    m = re.fullmatch(r"최신 기출문제 (\d+)회", r.get("set") or "")
    if m:
        r["printed_set"] = r["set"]
        r["set"] = JC_ROUNDS[section][int(m.group(1))]


def main():
    rows = []
    for f in sorted(PARTS.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        rows += data if isinstance(data, list) else data.get("pages", [])
    manifest = json.loads((PREPARED / "manifest.json").read_text(encoding="utf-8"))

    seen = Counter(r["file"] for r in rows)
    dupes = sorted(k for k, n in seen.items() if n > 1)
    missing = sorted(k for k in manifest if k not in seen)
    extra = sorted(k for k in seen if k not in manifest)
    rows = sorted({r["file"]: r for r in rows}.values(), key=lambda r: r["file"])
    last_part = {}
    for r in rows:
        if r["book"] == "jc":
            normalize_jc(r)
        # 소단원 띠가 없는 쪽은 같은 세트의 앞 쪽 소단원을 이어받는다 (한 쪽에 띠가 둘이면 마지막 것)
        key = (r["book"], r.get("set"))
        if r.get("part"):
            # 마지막 띠 제목만, "(23번부터)" 같은 메모 괄호는 떼고 제목의 괄호(UML(Unified …))는 살린다
            last = re.split(r"\s*(?:/|→)\s*", r["part"])[-1]
            last_part[key] = re.sub(r"\s*\([^)]*\d+\s*번[^)]*\)\s*$", "", last).strip()
        elif r.get("set") and r["type"] in ("question", "mixed", "explanation") and key in last_part:
            r["part"] = last_part[key]
            r["part_inferred"] = True
        # 재촬영본으로 바꾼 쪽: 메인 세션이 쪽 이미지를 다시 보고 확인한 뒤의 상태
        rep = manifest.get(r["file"], {}).get("replaces")
        if rep:
            r["reshot"] = True
            if r.get("quality", "ok") != "ok":
                r["note"] = f"재촬영본으로 교체(원래 {r['quality']}). " + (r.get("note") or "")
                r["quality"] = "ok"
    (ROOT / "data" / "pages.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"data/pages.json: {len(rows)}쪽")
    print(f"  빠진 쪽: {missing or '없음'}  중복: {dupes or '없음'}  모르는 파일: {extra or '없음'}")

    for book in sorted({r["book"] for r in rows}):
        br = [r for r in rows if r["book"] == book]
        print(f"\n[{book}] {len(br)}쪽 — 유형: {dict(Counter(r['type'] for r in br))}")
        sets = defaultdict(set)
        set_pages = defaultdict(list)
        for r in br:
            q = r.get("q_range")
            if r.get("set") and q and q[0] is not None and q[1] is not None and r["type"] in ("question", "mixed"):
                sets[r["set"]].update(range(q[0], q[1] + 1))
                set_pages[r["set"]].append(r["file"])
        for s in sorted(sets, key=lambda s: min(set_pages[s])):
            nums = sets[s]
            gaps = sorted(set(range(min(nums), max(nums) + 1)) - nums)
            flag = ""
            if book == "jc" and len(nums) != 100:
                flag = f"  ← 100문항 아님"
            sec = {r.get("section") for r in br if r.get("set") == s} - {None}
            sec = f" [{'해설 포함' if sec == {'with_explanation'} else '문제만'}]" if sec else ""
            print(f"  {s}{sec}: {min(nums)}~{max(nums)} ({len(nums)}문항, {set_pages[s][0]}~{set_pages[s][-1]})"
                  f"{'  빈 번호 ' + str(gaps) if gaps else ''}{flag}")
        no_set = [r["file"] for r in br if r["type"] in ("question", "mixed") and not r.get("set")]
        if no_set:
            print(f"  세트 미확인 문제 쪽: {no_set}")

        bad = [r for r in br if r.get("quality", "ok") != "ok"]
        if bad:
            print("  재촬영 추천:")
            by_src = defaultdict(list)
            for r in bad:
                src = manifest[r["file"]]["source"].rsplit("/", 1)[-1]
                by_src[src].append(f"{r['file']}({r['quality']}{': ' + r['note'] if r.get('note') else ''})")
            for src, items in by_src.items():
                print(f"    {src} ← {', '.join(items)}")
        pen = [r["file"] for r in br if "펜" in (r.get("note") or "")]
        if pen:
            print(f"  펜 표시 있는 쪽: {len(pen)}쪽")


if __name__ == "__main__":
    main()
