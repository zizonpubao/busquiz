"""문제 데이터 스키마 검사 (CLAUDE.md 스키마 기준).

사용법:
    python tools/validate.py data/questions
    python tools/validate.py data/sample --partial   # 샘플: 세트 완결성 검사는 정보로만

검사:
  - 필수 필드, 타입, id 형식({book}-s{2자리}-q{3자리})과 book/number 일치
  - subject(books.json에 책별 subjects가 있으면 그 목록) / flags 허용 목록, 보기 개수(data/books.json 책별), 보기 label 순서
  - answer / claude_answer 범위, answer=null <-> missing_answer 플래그
  - claude_answer != answer 이면 answer_conflict 플래그 + claude_note.conflict 필요
  - stem_images, choices[].image 파일이 data/assets/ 에 있는지
  - 세트 단위: 문항 번호 빠짐·겹침, 정처기(jc) 100문항·과목당 20문항
  - 스키마에 없는 필드(exam_source, difficulty 등)는 경고만

종료 코드: 오류가 있으면 1, 없으면 0.
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "data" / "assets"
BOOKS = ROOT / "data" / "books.json"

SUBJECTS = {"운영체제", "데이터베이스", "네트워크", "자료구조·알고리즘", "프로그래밍언어",
            "소프트웨어공학", "정보보안", "컴퓨터구조", "기타"}
FLAGS = {"low_confidence", "answer_conflict", "crop_check", "spans_pages",
         "missing_answer", "no_answer", "missing_explanation", "inferred"}
LABELS = ["①", "②", "③", "④", "⑤"]
REQUIRED = {
    "id": str, "book": str, "set": str, "number": int, "subject": str, "part": (str, type(None)),
    "stem": str, "passage": (str, type(None)), "stem_images": list, "code": (dict, type(None)),
    "table_md": (str, type(None)), "choices": list, "answer": (int, list, type(None)),
    "answer_source": (str, type(None)), "book_explanation": (str, type(None)),
    "claude_note": (dict, type(None)), "claude_answer": (int, list, type(None)), "source": dict,
    "flags": list, "duplicate_of": (str, type(None)),
    "exam_source": (str, type(None)), "difficulty": (str, type(None)),
}
KNOWN_EXTRA = {"inferred", "explanation_images"}
ANSWER_SOURCES = {"정답 표시", "정답 줄", "정답표", "해설 문장", "사용자 확정", "클로드 추론", "같은 문제 책 정답"}
DIFFICULTY = {"상", "중", "하"}
NOTE_KEYS = {"key_concept", "why_others_wrong", "trace", "extend", "conflict"}
CODE_LANGS = {"c", "cpp", "java", "python", "sql", "js", "javascript", "shell", "bash", "pseudo", "text"}
ID_RE = re.compile(r"^([a-z]{2})-s(\d{2})-q(\d{3})$")
PAGE_RE = re.compile(r"^[a-z]{2}-p\d{4}$")


def load_books():
    try:
        return {b["code"]: b for b in json.loads(BOOKS.read_text(encoding="utf-8"))}
    except Exception:
        return {}


def check_question(q, books, err, warn):
    qid = q.get("id", "?")

    def E(msg):
        err.append(f"{qid}: {msg}")

    def W(msg):
        warn.append(f"{qid}: {msg}")

    for k, t in REQUIRED.items():
        if k not in q:
            E(f"필수 필드 없음 `{k}`")
        elif not isinstance(q[k], t) or (t is int and isinstance(q[k], bool)):
            E(f"`{k}` 타입 오류 ({type(q[k]).__name__})")
    for k in q:
        if k not in REQUIRED and k not in KNOWN_EXTRA:
            W(f"스키마 밖 필드 `{k}`")
    if q.get("inferred") is not None:
        if not isinstance(q["inferred"], list) or "inferred" not in (q.get("flags") or []):
            E("`inferred` 기록이 배열이 아니거나 inferred 플래그 없음")

    m = ID_RE.match(str(q.get("id", "")))
    if not m:
        E("id 형식 오류 (예: gs-s03-q017)")
    else:
        if q.get("book") != m.group(1):
            E(f"id 책코드 {m.group(1)} != book {q.get('book')}")
        if isinstance(q.get("number"), int) and q["number"] != int(m.group(3)):
            E(f"id 문항번호 {int(m.group(3))} != number {q['number']}")

    book = books.get(q.get("book"))
    if books and not book:
        E(f"books.json에 없는 책 코드 `{q.get('book')}`")

    allowed = set((book or {}).get("subjects") or SUBJECTS)
    if q.get("subject") not in allowed:
        E(f"subject `{q.get('subject')}` 는 {'책 과목 목록' if (book or {}).get('subjects') else '공통 목록'}에 없음")
    if q.get("part") in (None, ""):
        W("part 비어 있음")
    if not str(q.get("stem", "")).strip():
        E("stem 비어 있음")

    # 보기
    choices = q.get("choices") or []
    allowed = (book or {}).get("choices", [4, 5])
    if len(choices) not in allowed:
        E(f"보기 {len(choices)}개 (허용 {allowed})")
    for i, c in enumerate(choices):
        if not isinstance(c, dict):
            E(f"보기 {i+1} 형식 오류")
            continue
        if i < len(LABELS) and c.get("label") != LABELS[i]:
            E(f"보기 {i+1} label `{c.get('label')}` (기대 {LABELS[i]})")
        if not str(c.get("text") or "").strip() and not c.get("image"):
            E(f"보기 {i+1} 텍스트·이미지 모두 비어 있음")
        if c.get("image") and not (ASSETS / c["image"]).is_file():
            E(f"보기 {i+1} 이미지 없음 data/assets/{c['image']}")

    # 정답
    flags = q.get("flags") or []
    for f in flags:
        if f not in FLAGS:
            E(f"알 수 없는 flag `{f}`")
    if len(set(flags)) != len(flags):
        W("flags 중복")
    n = len(choices)
    ans, cans = q.get("answer"), q.get("claude_answer")
    if q.get("difficulty") not in (None, *DIFFICULTY):
        E(f"difficulty `{q.get('difficulty')}` (상/중/하)")
    # 추출 단계(정답·해설 아직 없음)면 정답 검사는 건너뛴다
    answered = any(q.get(k) is not None for k in ("answer_source", "book_explanation", "claude_answer", "claude_note"))

    def in_range(v):
        vs = v if isinstance(v, list) else [v]
        return all(isinstance(x, int) and 1 <= x <= n for x in vs) and (not isinstance(v, list) or len(v) >= 2)

    if answered:
        if ans is None:
            if not ({"missing_answer", "no_answer"} & set(flags)):
                E("answer=null 인데 missing_answer/no_answer 플래그 없음")
        else:
            if not in_range(ans):
                E(f"answer {ans} 범위 밖 (1~{n}, 복수 정답은 2개 이상 배열)")
            if {"missing_answer", "no_answer"} & set(flags):
                E("answer가 있는데 missing_answer/no_answer 플래그가 남아 있음")
            if q.get("answer_source") not in ANSWER_SOURCES:
                E(f"answer_source `{q.get('answer_source')}` ({' / '.join(sorted(ANSWER_SOURCES))})")
    if cans is not None and not in_range(cans):
        E(f"claude_answer {cans} 범위 밖 (1~{n})")
    note = q.get("claude_note") or {}
    if ans is not None and cans is not None and ans != cans:
        if "answer_conflict" not in flags:
            E(f"answer {ans} != claude_answer {cans} 인데 answer_conflict 플래그 없음")
        if not note.get("conflict"):
            E("정답 충돌인데 claude_note.conflict 근거 없음")
    if "answer_conflict" in flags and (ans is None or ans == cans):
        W("answer_conflict 플래그가 있지만 answer와 claude_answer가 같거나 answer 없음")
    if isinstance(note, dict):
        for k in note:
            if k not in NOTE_KEYS:
                W(f"claude_note 알 수 없는 키 `{k}`")
        wow = note.get("why_others_wrong") or {}
        for k in wow:
            if not str(k).isdigit() or not 1 <= int(k) <= n:
                E(f"why_others_wrong 키 `{k}` 범위 밖")
        if q.get("book") == "jc" and note and not note.get("extend"):
            W("정처기 문항인데 claude_note.extend 없음")
        if q.get("code") and note and not note.get("trace"):
            W("코드 문제인데 claude_note.trace 없음")
    if not q.get("book_explanation") and "missing_explanation" not in flags:
        W("book_explanation 비어 있음 (missing_explanation 플래그 없음)")

    # 코드·이미지
    code = q.get("code")
    if isinstance(code, dict):
        if not str(code.get("text") or "").strip():
            E("code.text 비어 있음")
        lang = code.get("lang")
        if lang not in CODE_LANGS:
            W(f"code.lang `{lang}` 확인")
        if not q.get("stem_images"):
            W("코드가 있는데 원본 크롭 이미지(stem_images)가 없음 (CLAUDE.md 규칙 4)")
    for img in q.get("stem_images") or []:
        if not (ASSETS / img).is_file():
            E(f"stem_images 파일 없음 data/assets/{img}")

    # 출처
    src = q.get("source") or {}
    qp = src.get("question_pages")
    if not qp:
        E("source.question_pages 비어 있음")
    for p in (qp or []) + (src.get("answer_pages") or []):
        if not PAGE_RE.match(str(p)) or not str(p).startswith(f"{q.get('book')}-"):
            E(f"source 쪽 이름 `{p}` 형식/책코드 오류")
    if qp and len(qp) > 1 and "spans_pages" not in flags:
        W("문제 쪽이 2쪽 이상인데 spans_pages 플래그 없음")
    if "printed_page" not in src:
        W("source.printed_page 없음")
    if q.get("duplicate_of") and not ID_RE.match(q["duplicate_of"]):
        E(f"duplicate_of `{q['duplicate_of']}` id 형식 오류")


def check_sets(qs, books, out):
    """세트 단위: 번호 빠짐·겹침, jc 100문항·과목당 20문항."""
    by_set = defaultdict(list)
    for q in qs:
        m = ID_RE.match(str(q.get("id", "")))
        key = (q.get("book"), m.group(2) if m else "?")
        by_set[key].append(q)
    for (book, s), items in sorted(by_set.items()):
        tag = f"{book}-s{s}"
        names = {q.get("set") for q in items}
        if len(names) > 1:
            out.append(f"{tag}: 같은 세트 번호에 set 이름이 여러 개 {sorted(map(str, names))}")
        nums = [q.get("number") for q in items if isinstance(q.get("number"), int)]
        dup = [n for n, c in Counter(nums).items() if c > 1]
        if dup:
            out.append(f"{tag}: 문항 번호 겹침 {sorted(dup)}")
        if nums:
            lo = 1
            hi = max(nums)
            info = books.get(book, {})
            if info.get("questions_per_set"):
                hi = max(hi, info["questions_per_set"])
            missing = sorted(set(range(lo, hi + 1)) - set(nums))
            if missing:
                shown = missing if len(missing) <= 20 else missing[:20] + ["…"]
                out.append(f"{tag}: 문항 번호 빠짐 {len(missing)}개 {shown}")
        info = books.get(book, {})
        if info.get("questions_per_set") and len(items) != info["questions_per_set"]:
            out.append(f"{tag}: {len(items)}문항 (기대 {info['questions_per_set']})")
        if info.get("questions_per_subject"):
            per = Counter(q.get("part") for q in items)
            for part, c in sorted(per.items(), key=lambda x: str(x[0])):
                if c != info["questions_per_subject"]:
                    out.append(f"{tag}: 과목 `{part}` {c}문항 (기대 {info['questions_per_subject']})")
    return by_set


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", help="문제 JSON 폴더 (예: data/questions, data/sample)")
    ap.add_argument("--partial", action="store_true",
                    help="일부만 뽑은 데이터: 세트 완결성(빠짐·문항 수) 결과를 오류가 아닌 정보로 표시")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    folder = Path(args.folder)
    if not folder.is_absolute():
        folder = (Path.cwd() / folder).resolve()
    files = sorted(p for p in folder.glob("*.json") if not p.name.startswith("_"))
    if not files:
        print(f"JSON 파일 없음: {folder}")
        return 1

    books = load_books()
    err, warn, qs = [], [], []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            err.append(f"{f.name}: JSON 읽기 실패 {e}")
            continue
        if not isinstance(data, list):
            err.append(f"{f.name}: 최상위가 배열이 아님")
            continue
        for q in data:
            if not isinstance(q, dict):
                err.append(f"{f.name}: 배열 원소가 객체가 아님")
                continue
            qs.append(q)
            check_question(q, books, err, warn)
            m = ID_RE.match(str(q.get("id", "")))
            if m and not f.stem.startswith(f"{m.group(1)}-s{m.group(2)}"):
                warn.append(f"{q.get('id')}: 파일 {f.name} 과 세트가 다름")

    ids = Counter(q.get("id") for q in qs)
    for i, c in ids.items():
        if c > 1:
            err.append(f"{i}: id 중복 {c}회")

    set_issues = []
    by_set = check_sets(qs, books, set_issues)
    if not args.partial:
        err.extend(set_issues)

    print(f"검사: {folder} — 파일 {len(files)}개, 문항 {len(qs)}개, 세트 {len(by_set)}개")
    print(f"오류 {len(err)}건")
    for e in err:
        print(f"  [오류] {e}")
    print(f"경고 {len(warn)}건")
    for w in warn:
        print(f"  [경고] {w}")
    if args.partial:
        print(f"세트 완결성 (--partial, 정보만) {len(set_issues)}건")
        for s in set_issues:
            print(f"  [정보] {s}")
    return 1 if err else 0


if __name__ == "__main__":
    sys.exit(main())
