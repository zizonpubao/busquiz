"""세트 파일(data/questions/*.json)의 표기를 data/decisions.json rules에 맞게 통일한다.

여러 번 돌려도 결과가 같다(멱등). 고친 내용과 사람이 볼 곳을 출력한다.
- 진법 유니코드 아래첨자 F9₁₆, 13754₍₈₎ → F9(16), 13754(8)
- 부울 NOT ′ → ', 마이너스 − → - (표 빈칸 줄표 – 는 그대로)
- 프로그램 코드(c·cpp·java·python·sql·shell) 안 ≤ ≥ 〈 〉 → <= >= < > (pseudo는 그대로)
- code.lang pseudo 중 셸 명령 상자 → shell
- part가 pages.json 소단원 제목의 앞부분이면(괄호가 잘린 것) 전체 제목으로
- data/extract_followups.md의 문항별 고칠 것 중 기계적으로 되는 것
보고만: code.text 안의 '^'(위첨자를 잘못 바꿨을 수 있음), 남은 pseudo

사용: python tools/normalize_questions.py          고치고 저장
      python tools/normalize_questions.py --dry    보고만
"""
import json, re, sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
QDIR = ROOT / "data" / "questions"

SUB = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
SUB_RE = re.compile(r"₍?([₀-₉]+)₎?")
# (1001)(2) → 1001(2): 진법 표기에서 수 쪽 괄호는 뗀다
BASE_PAREN_RE = re.compile(r"\(([0-9A-Fa-f.]{2,})\)\((2|8|10|16)\)")
SHELL_IDS ={"jc-s01-q066", "gs-s02-q171", "gs-s02-q172", "gs-s02-q174"}
SHELL_WORDS = re.compile(r"^\s*(\$ |# )?(ls|chmod|chown|cd|cat|grep|ps|kill|mkdir|rm|cp|mv|umask|echo|find|tar|vi|ln)\b", re.M)
# 조판 공백 연산자('- -' → '--')는 추출 단계에서 사람 눈으로 처리한다. 기계적으로 붙이면
# 'i-- + ++j' 같은 정상 코드가 'i-- +++j'로 깨진다 (gs-s07-q037, 2026-10-18)
PROGRAM_LANGS = {"c", "cpp", "java", "python", "sql", "shell"}
# 코드 안에서 볼 만한 비ASCII 기호 (한글·위첨자 숫자·←는 정상)
ODD_RE = re.compile(r"[^\x00-\x7f가-힣ㄱ-ㅎㅏ-ㅣ²³¹⁰-⁹←①-⑳㉠-㉭\s]")
# 문항별 기계적 수정: (id, 필드 경로, 바꿀 것, 바꿀 값)
FIXES = [
    ("gs-s04-q012", "code.text", "2^2", "2²"),
    ("jc-s08-q097", "choices.0.text", "Manage-ment", "Management"),
    ("jc-s02-q075", "code.text", "\n       ", "\n    "),  # 들여쓰기 7칸 → 4칸
]


def fix_text(s):
    if not isinstance(s, str):
        return s
    s = SUB_RE.sub(lambda m: f"({m.group(1).translate(SUB)})", s)
    s = BASE_PAREN_RE.sub(r"\1(\2)", s)
    return s.replace("′", "'").replace("−", "-")


def fix_code(s, lang):
    s = fix_text(s)
    # 의사코드·관계대수(pseudo)의 ≤는 수학 기호라 그대로 둔다
    if lang in PROGRAM_LANGS:
        s = s.replace("≤", "<=").replace("≥", ">=").replace("〈", "<").replace("〉", ">")
    return s


def part_titles():
    pages = json.loads((ROOT / "data" / "pages.json").read_text(encoding="utf-8"))
    titles = defaultdict(set)
    for p in pages:
        if p.get("part"):
            for t in re.split(r"\s*(?:/|→)\s*", p["part"]):
                t = re.sub(r"\s*\([^)]*\d+\s*번[^)]*\)\s*$", "", t).strip()
                if t:
                    titles[p["book"]].add(t)
    return titles


def get_path(q, path):
    cur = q
    keys = path.split(".")
    for k in keys[:-1]:
        cur = cur[int(k)] if k.isdigit() else cur.get(k)
        if cur is None:
            return None, None
    return cur, (int(keys[-1]) if keys[-1].isdigit() else keys[-1])


def normalize(q, titles, log):
    before = json.dumps(q, ensure_ascii=False)
    for k in ("stem", "passage", "table_md", "book_explanation", "exam_source"):
        q[k] = fix_text(q.get(k))
    for ch in q.get("choices") or []:
        ch["text"] = fix_text(ch.get("text"))
    code = q.get("code")
    if code and code.get("text"):
        code["text"] = fix_code(code["text"], code.get("lang"))
        if code.get("lang") == "pseudo" and (q["id"] in SHELL_IDS or SHELL_WORDS.search(code["text"])):
            code["lang"] = "shell"
            log["pseudo→shell"].append(q["id"])
    part = q.get("part")
    if part and part not in titles[q["book"]]:
        longer = sorted(t for t in titles[q["book"]] if t.startswith(part) and t[len(part):len(part) + 1] in "( ")
        if len(longer) == 1:
            q["part"] = longer[0]
            log["part 복원"].append(f"{q['id']}: {part} → {longer[0]}")
    for qid, path, old, new in FIXES:
        if q["id"] == qid:
            obj, key = get_path(q, path)
            if obj is not None and isinstance(obj[key], str) and old in obj[key]:
                obj[key] = obj[key].replace(old, new)
                log["문항별 수정"].append(f"{qid} {path}: {old} → {new}")
    if code and "^" in (code.get("text") or ""):
        log["확인: 코드 안 ^"].append(q["id"])
    if code and code.get("lang") == "pseudo":
        log["확인: 남은 pseudo"].append(q["id"])
    odd = sorted(set(ODD_RE.findall((code or {}).get("text") or "")))
    if odd:
        log["확인: 코드 안 특수 기호"].append(f"{q['id']} {''.join(odd)}")
    return json.dumps(q, ensure_ascii=False) != before


def main():
    dry = "--dry" in sys.argv
    titles = part_titles()
    log = defaultdict(list)
    for f in sorted(QDIR.glob("*.json")):
        qs = json.loads(f.read_text(encoding="utf-8"))
        changed = [q["id"] for q in qs if normalize(q, titles, log)]
        if changed:
            print(f"{f.name}: {len(changed)}문항 고침")
            if not dry:
                f.write_text(json.dumps(qs, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, items in log.items():
        print(f"\n[{k}] {len(items)}")
        for it in items:
            print("  ", it)
    if dry:
        print("\n(--dry: 저장 안 함)")


if __name__ == "__main__":
    main()
