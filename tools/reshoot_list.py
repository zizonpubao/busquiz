"""추출 결과에서 재촬영이 필요한 쪽을 원본 사진 번호로 모은다 → data/reshoot-extract.md

[판독불가]가 발문·지문·보기·코드·표에 있으면 "본문", 출처(exam_source)에만 있으면 "출처만"으로 나눈다.
본문 잘림이 있는 원본 사진을 잘린 문항 수가 많은 순으로 보여 준다.
사용: python tools/reshoot_list.py
"""
import json, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
MARK = "[판독불가]"


def body_fields(q):
    yield "발문", q.get("stem")
    yield "지문", q.get("passage")
    yield "표", q.get("table_md")
    yield "코드", (q.get("code") or {}).get("text")
    for i, ch in enumerate(q.get("choices") or [], 1):
        yield f"보기{i}", ch.get("text")


def main():
    manifest = json.loads((ROOT / "scans" / "prepared" / "manifest.json").read_text(encoding="utf-8"))
    qs = [q for f in sorted((ROOT / "data" / "questions").glob("*.json"))
          for q in json.loads(f.read_text(encoding="utf-8"))]
    flags = Counter(fl for q in qs for fl in q.get("flags") or [])
    body, src_only = [], []
    for q in qs:
        where = [name for name, t in body_fields(q) if t and MARK in t]
        if where:
            body.append((q, where))
        elif MARK in (q.get("exam_source") or ""):
            src_only.append(q)

    by_photo = defaultdict(list)
    for q, where in body:
        for p in q["source"]["question_pages"]:
            m = manifest.get(p, {})
            photo = m.get("source", p).rsplit("/", 1)[-1]
            side = {"L": "왼쪽", "R": "오른쪽"}.get(m.get("half"), "")
            by_photo[(q["book"], photo)].append((q["id"], p, side, where))

    out = ["# 추출 후 재촬영 후보 (자동 생성: tools/reshoot_list.py)", "",
           f"문항 {len(qs)}개 · 플래그 {dict(flags)}",
           f"본문에 [판독불가]가 있는 문항 {len(body)}개 · 출처에만 있는 문항 {len(src_only)}개", "",
           "## 본문 잘림 — 원본 사진별 (잘린 문항 많은 순)", ""]
    for (book, photo), items in sorted(by_photo.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        pages = sorted({f"{p}{'(' + s + ')' if s else ''}" for _, p, s, _ in items})
        out.append(f"- **{book} / {photo}** — {', '.join(pages)} — {len(items)}문항")
        for qid, _, _, where in items:
            out.append(f"  - {qid}: {', '.join(where)}")
    # 정답 숫자가 안 보인 문항: 책 정답 없음(missing_answer, 문제만 구역 제외) / 해설 문장으로 채움
    ans_photo = defaultdict(lambda: {"없음": [], "해설": []})
    for q in qs:
        only_q = q["book"] == "jc" and int(q["id"][4:6]) >= 6
        kind = ("없음" if ("missing_answer" in (q.get("flags") or []) or q.get("answer_source") == "클로드 추론") and not only_q
                else "해설" if q.get("answer_source") == "해설 문장" else None)
        if not kind:
            continue
        pages = q["source"].get("answer_pages") or q["source"]["question_pages"]
        for p in pages[:1]:
            photo = manifest.get(p, {}).get("source", p).rsplit("/", 1)[-1]
            ans_photo[(q["book"], photo)][kind].append(q["id"])
    out += ["", "## 정답 숫자 잘림 — 원본 사진별", "",
            "**없음** = 책 정답을 못 읽어 클로드 풀이로 채움(책 정답 미확인), "
            "**해설** = 해설 문장으로 채웠지만 숫자로 확인하면 좋음", ""]
    for (book, photo), d in sorted(ans_photo.items(), key=lambda kv: (-len(kv[1]["없음"]), kv[0])):
        both = by_photo.get((book, photo))
        out.append(f"- **{book} / {photo}** — 없음 {len(d['없음'])} · 해설 {len(d['해설'])}"
                   + (" · (본문 잘림 목록에도 있음)" if both else ""))
        if d["없음"]:
            out.append(f"  - 없음: {', '.join(d['없음'])}")
        if d["해설"]:
            out.append(f"  - 해설: {', '.join(d['해설'])}")
    all_photos = set(by_photo) | set(ans_photo)
    out += ["", f"## 합계: 다시 찍을 사진 {len(all_photos)}장 "
            f"(gs {sum(1 for b, _ in all_photos if b == 'gs')}, jc {sum(1 for b, _ in all_photos if b == 'jc')})", ""]
    out += ["", "## 출처(exam_source)만 잘린 문항", "",
            ", ".join(q["id"] for q in src_only) or "없음", ""]
    (ROOT / "data" / "reshoot-extract.md").write_text("\n".join(out), encoding="utf-8")
    print(f"data/reshoot-extract.md: 사진 {len(by_photo)}장, 본문 잘림 {len(body)}문항, 출처만 {len(src_only)}문항")
    print("책별 사진 수:", dict(Counter(b for b, _ in by_photo)))
    print("책별 문항 수:", dict(Counter(q["book"] for q, _ in body)))
    print("플래그:", dict(flags))


if __name__ == "__main__":
    main()
