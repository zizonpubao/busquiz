"""책 사이 중복(유사) 문제 찾기.

사용법:
    python tools/find_dupes.py data/questions
    python tools/find_dupes.py data/questions --threshold 0.85 --same-book

발문+보기(+코드)를 합쳐 공백·기호를 지우고 문자 유사도(difflib)를 잰다.
기본은 **서로 다른 책** 사이만 비교한다. 유사도 >= threshold(기본 0.85)인 쌍을 출력.
duplicate_of 기록은 하지 않는다 (사용자 확인 뒤 메인 세션이 한다).
"""
import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

STRIP = re.compile(r"[\s\W_]+", re.UNICODE)  # 공백·기호 제거 (한글·영문·숫자만 남김)


def norm(s):
    return STRIP.sub("", s or "").lower()


def text_of(q):
    parts = [q.get("stem", "")]
    code = q.get("code")
    if isinstance(code, dict):
        parts.append(code.get("text", ""))
    parts += [c.get("text") or "" for c in q.get("choices") or [] if isinstance(c, dict)]
    return norm("".join(parts))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--threshold", type=float, default=0.85)
    ap.add_argument("--same-book", action="store_true", help="같은 책 안의 쌍도 비교")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    qs = []
    for f in sorted(Path(args.folder).glob("*.json")):
        if f.name.startswith("_"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[건너뜀] {f.name}: {e}")
            continue
        for q in data if isinstance(data, list) else []:
            if isinstance(q, dict):
                qs.append((q.get("id"), q.get("book"), text_of(q)))

    pairs, compared = [], 0
    for i in range(len(qs)):
        for j in range(i + 1, len(qs)):
            a, b = qs[i], qs[j]
            if a[1] == b[1] and not args.same_book:
                continue
            if not a[2] or not b[2]:
                continue
            la, lb = len(a[2]), len(b[2])
            if min(la, lb) / max(la, lb) < args.threshold:  # 길이 차이만으로 기준 미달
                compared += 1
                continue
            sm = SequenceMatcher(None, a[2], b[2], autojunk=False)
            compared += 1
            if sm.real_quick_ratio() < args.threshold or sm.quick_ratio() < args.threshold:
                continue
            r = sm.ratio()
            if r >= args.threshold:
                pairs.append((r, a[0], b[0]))

    pairs.sort(reverse=True)
    print(f"문항 {len(qs)}개, 비교 {compared}쌍, 유사도 {args.threshold} 이상 {len(pairs)}쌍")
    for r, x, y in pairs:
        print(f"  {r:.3f}  {x}  <->  {y}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
