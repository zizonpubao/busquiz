"""question-extractor 분담 계획을 만든다 → data/extract_plan.json

세트마다 문항이 '시작하는' 쪽을 기준으로 문항 번호 범위를 겹치지 않게 나눈다.
같은 쪽을 두 번 찍은 경우(이미 배정된 문항만 있는 쪽)는 건너뛴다.
조각마다 그 문항들이 걸친 쪽 + 다음 쪽(넘어가는 문제·보기 확인용)을 준다.

사용: python tools/plan_extract.py [--gs 28] [--jc 40]
"""
import argparse, json, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gs", type=int, default=28, help="gs 조각당 목표 문항 수")
    ap.add_argument("--jc", type=int, default=40, help="jc 조각당 목표 문항 수")
    a = ap.parse_args()
    target = {"gs": a.gs, "jc": a.jc}

    pages = json.loads((ROOT / "data" / "pages.json").read_text(encoding="utf-8"))
    order = {p["file"]: i for i, p in enumerate(pages)}
    set_no, plan = {}, []
    for book in ("gs", "jc"):
        sets = []
        for p in pages:
            if p["book"] == book and p.get("set") and p["set"] not in sets and p["type"] in ("question", "mixed"):
                sets.append(p["set"])
        for i, s in enumerate(sets, 1):
            set_no[(book, s)] = i
            # 문항 → 시작 쪽, 문항이 나오는 모든 쪽
            start, seen_on = {}, {}
            for p in pages:
                if p["book"] != book or p.get("set") != s or p["type"] not in ("question", "mixed", "explanation"):
                    continue
                q = p.get("q_range")
                if not q or q[0] is None or q[1] is None:
                    continue
                cont = (p.get("continues") or {}).get("from_prev")
                for n in range(q[0], q[1] + 1):
                    seen_on.setdefault(n, []).append(p["file"])
                    if n not in start and n != cont and p["type"] != "explanation":
                        start[n] = p["file"]
            nums = sorted(start)
            chunk = []
            for idx, n in enumerate(nums):
                chunk.append(n)
                last = idx == len(nums) - 1
                # 같은 쪽에서 시작하는 문항은 한 조각에 둔다
                if last or (len(chunk) >= target[book] and start[nums[idx + 1]] != start[n]):
                    files = sorted({f for k in chunk for f in seen_on[k]}, key=order.get)
                    nxt = pages[order[files[-1]] + 1]["file"] if order[files[-1]] + 1 < len(pages) else None
                    if nxt and pages[order[nxt]]["book"] == book:
                        files.append(nxt)
                    sid = f"{book}-s{i:02d}"
                    plan.append({
                        "book": book, "set": s, "set_id": sid, "q_from": chunk[0], "q_to": chunk[-1],
                        "count": len(chunk), "pages": files,
                        "out": f"data/questions/_parts/{sid}-q{chunk[0]:03d}-q{chunk[-1]:03d}.json",
                    })
                    chunk = []

    (ROOT / "data" / "extract_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    for book in ("gs", "jc"):
        ch = [c for c in plan if c["book"] == book]
        print(f"{book}: {len(ch)}조각, {sum(c['count'] for c in ch)}문항, "
              f"조각당 {min(c['count'] for c in ch)}~{max(c['count'] for c in ch)}문항 / "
              f"{min(len(c['pages']) for c in ch)}~{max(len(c['pages']) for c in ch)}쪽")
    print(f"세트 순번: " + ", ".join(f"{b}-s{n:02d}={s}" for (b, s), n in set_no.items()))


if __name__ == "__main__":
    main()
