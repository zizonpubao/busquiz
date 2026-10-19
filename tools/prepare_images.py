"""scans/raw/<책코드>/ 원본을 쪽 단위 이미지 scans/prepared/<책코드>-p0001.jpg … 로 정리한다.

- 사진(HEIC/JPG/PNG/WEBP): EXIF 회전 보정. PDF: 페이지마다 200dpi로 렌더링
- 방향: 펼친 면을 폰을 세운 채 찍어서 대부분 시계 방향으로 90° 누워 있다.
  글줄 방향을 판별해 누운 것만 반시계 90° 돌린다 (OCR 없이 픽셀 분포로 판별)
- 쪽 나누기: 돌린 뒤 가로가 더 길면 펼친 면으로 보고 왼쪽/오른쪽 쪽으로 나눈다.
  접힌 곳 후보를 세 방법(글자 적은 곳, 빈 띠, 접힌 곳 그림자)으로 구해 그 범위 전체를 양쪽 쪽에 넣는다.
  그래서 쪽 안쪽 가장자리에 옆 쪽 내용이 조금 보일 수 있다 (추출 때 무시할 것)
- 판별이 틀리면 data/prep_overrides.json 에 원본별로 적어 바로잡는다:
    { "gs/박미진 컴퓨터일반 기출 - 89.jpg": {"rotate": 0, "split": false},
      "jc/…pdf#3": {"rotate": 90, "split": true, "split_at": 0.52} }
  rotate는 반시계 방향 각도(0/90/180/270), split_at은 왼쪽에서부터의 비율.
  재촬영본은 "replace_with": "reshoot/재촬영 - 3.jpg" (scans/raw 기준)로 지정하면
  원본 자리(순서·쪽 번호)를 그대로 쓰고 그 파일을 대신 읽는다. 원본은 지우지 않는다
- 순서: 책의 모든 사진에 EXIF 촬영 시각이 있으면 그 순서, 아니면 파일명 자연 정렬("- 2" < "- 10").
  펼친 면은 왼쪽 쪽 → 오른쪽 쪽
- 긴 변이 2400px보다 크면 2400px로 줄임
- 원본은 읽기만 한다
- 결과 대응표: scans/prepared/manifest.json (쪽 이미지 → 원본, 회전, 왼/오른쪽)

사용: python tools/prepare_images.py [책코드 ...]   (생략하면 data/books.json의 모든 책)
"""
import json, re, sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
import pillow_heif

pillow_heif.register_heif_opener()
sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "scans" / "raw"
OUT = ROOT / "scans" / "prepared"
OVERRIDES = ROOT / "data" / "prep_overrides.json"
MAX_SIDE = 2400
JPEG_QUALITY = 90
PDF_DPI = 200
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}
UPRIGHT_RATIO = 0.85   # 열/행 프로파일 들쭉날쭉함 비율이 이보다 작으면 가로줄(바로 섬)
OVERLAP = 0.015        # 접힌 곳 후보 범위 바깥으로 더 겹치는 폭 (펼친 면 너비 대비)
AGREE = 0.03           # 두 후보가 이만큼 이내면 일치로 본다
MAX_EDGE = (0.38, 0.62)  # 겹침이 아무리 넓어도 오른쪽 쪽은 38% 이후에서 시작, 왼쪽 쪽은 62% 전에 끝


def natural_key(name):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def exif_time(path):
    try:
        with Image.open(path) as im:
            exif = im.getexif()
            raw = exif.get_ifd(0x8769).get(36867) or exif.get(306)  # DateTimeOriginal, DateTime
        return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S") if raw else None
    except Exception:
        return None


def load(src, page):
    if page is None:
        with Image.open(src) as im:
            return ImageOps.exif_transpose(im).convert("RGB")
    import pymupdf
    with pymupdf.open(src) as doc:
        pix = doc[page].get_pixmap(dpi=PDF_DPI)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def ink_mask(im):
    g = im.convert("L")
    g.thumbnail((1200, 1200))
    a = np.asarray(g, dtype=np.float32)
    return (a < np.median(a) - 50).astype(np.float32)


def jaggedness(profile):
    return np.abs(np.diff(profile)).mean() / (profile.mean() + 1e-6)


def find_gutter(ink):
    """펼친 면에서 두 쪽의 글자 덩어리 사이 빈 띠를 찾는다.

    위아래 10%를 뺀 높이에서 글자가 거의 없는 세로줄들의 연속 구간을 찾고,
    접힌 곳 그림자처럼 가는 선(너비 1.5% 이하)으로 끊긴 구간은 하나로 잇는다.
    중심이 가운데(40~60%)에 있는 가장 넓은 빈 띠를 고른다.
    반환: (나눌 위치, 왼쪽 쪽 끝, 오른쪽 쪽 시작) — 너비 대비 비율. 못 찾으면 None
    """
    h, w = ink.shape
    cols = ink[h // 10: -h // 10].mean(axis=0)
    blank = cols < 0.004
    runs, start = [], None
    for x, b in enumerate(list(blank) + [False]):
        if b and start is None:
            start = x
        elif not b and start is not None:
            runs.append([start, x])
            start = None
    merged = []
    for r in runs:
        if merged and r[0] - merged[-1][1] <= w * 0.015:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    # 접힌 곳은 실제로 가운데 45~52% 근처. 범위를 넓히면 한 쪽 안의 단 사이 빈 공간을 잘못 잡는다
    cand = [r for r in merged if r[1] - r[0] >= w * 0.01 and w * 0.4 <= (r[0] + r[1]) / 2 <= w * 0.6]
    if not cand:
        return None
    a, b = max(cand, key=lambda r: r[1] - r[0])
    return (a + b) / 2 / w, a / w, b / w


def find_gutter_fallback(ink):
    """가운데 40~60% 중 글자가 가장 적은 세로줄."""
    cols = ink.mean(axis=0)
    w = len(cols)
    k = max(3, w // 50)
    smooth = np.convolve(cols, np.ones(k) / k, mode="same")
    lo, hi = int(w * 0.4), int(w * 0.6)
    return (lo + int(np.argmin(smooth[lo:hi]))) / w


def find_fold_shadow(im):
    """가운데 42~58% 중, 주변보다 가늘게 어두운 세로선(접힌 곳 그림자) 위치."""
    g = im.convert("L")
    g.thumbnail((1600, 1600))
    a = np.asarray(g, dtype=np.float32)
    h, w = a.shape
    dark = 255 - a[h // 10: -h // 10].mean(axis=0)

    def sm(x, k):
        return np.convolve(x, np.ones(k) / k, mode="same")

    line = sm(dark, max(3, w // 300)) - sm(dark, max(5, w // 15))
    lo, hi = int(w * 0.42), int(w * 0.58)
    return (lo + int(np.argmax(line[lo:hi]))) / w


def analyze(job):
    """원본 하나 → 회전 각도, 쪽 나누기 여부·위치."""
    key, src, page, override = job
    try:
        im = load(src, page)
        ink = ink_mask(im)
        ratio = jaggedness(ink.mean(axis=0)) / jaggedness(ink.mean(axis=1))
        rotate = override.get("rotate", 0 if ratio < UPRIGHT_RATIO else 90)
        if rotate:
            im = im.rotate(rotate, expand=True)
            ink = ink_mask(im)
        w, h = im.size
        split = override.get("split", w > h)
        d = {"key": key, "rotate": rotate, "split": split, "ratio": round(float(ratio), 3),
             "overridden": bool(override)}
        if split:
            if "split_at" in override:
                m = override["split_at"]
                d.update(split_at=m, gutter="override", l_end=m + OVERLAP, r_start=m - OVERLAP)
            else:
                # 방법마다 틀리는 사진이 달라서(단 사이 빈칸, 세로 괘선, 비친 글씨 …)
                # 두 후보가 AGREE 이내로 일치하면 그 둘을, 셋 다 다르면 전부를 감싸는 범위를
                # 양쪽 쪽에 다 넣는다 → 맞는 후보가 범위 안에 있으면 글자가 안 잘림
                band = find_gutter(ink)
                cands = {"min_ink": find_gutter_fallback(ink), "shadow": find_fold_shadow(im)}
                spans = {k: (v, v) for k, v in cands.items()}
                if band:
                    cands["band"] = band[0]
                    spans["band"] = (band[1], band[2])
                names = list(cands)
                pairs = sorted((abs(cands[a] - cands[b]), a, b)
                               for i, a in enumerate(names) for b in names[i + 1:])
                chosen = pairs[0][1:] if pairs[0][0] <= AGREE else names
                lo = min(spans[k][0] for k in chosen)
                hi = max(spans[k][1] for k in chosen)
                d.update(split_at=float(np.mean([cands[k] for k in chosen])),
                         candidates={k: round(v, 4) for k, v in cands.items()},
                         gutter="+".join(chosen) if len(chosen) == 2 else "all_differ",
                         l_end=min(hi + OVERLAP, MAX_EDGE[1]), r_start=max(lo - OVERLAP, MAX_EDGE[0]))
            d["l_end"], d["r_start"] = round(min(1.0, d["l_end"]), 4), round(max(0.0, d["r_start"]), 4)
        return d
    except Exception as e:
        return {"key": key, "error": f"{type(e).__name__}: {e}"}


def render(job):
    """결정된 회전·나누기대로 쪽 이미지를 저장."""
    src, page, rotate, crops = job
    try:
        im = load(src, page)
        if rotate:
            im = im.rotate(rotate, expand=True)
        w, h = im.size
        for (x0, x1), dest in crops:
            part = im.crop((round(x0 * w), 0, round(x1 * w), h))
            if max(part.size) > MAX_SIDE:
                s = MAX_SIDE / max(part.size)
                part = part.resize((round(part.width * s), round(part.height * s)), Image.LANCZOS)
            part.save(dest, "JPEG", quality=JPEG_QUALITY, optimize=True)
        return None
    except Exception as e:
        return f"{src} → {type(e).__name__}: {e}"


def plan_book(code):
    files = [f for f in (RAW / code).iterdir() if f.is_file()]
    images = [f for f in files if f.suffix.lower() in IMAGE_EXT]
    pdfs = [f for f in files if f.suffix.lower() == ".pdf"]
    skipped = [f.name for f in files if f not in images and f not in pdfs]

    times = {f: exif_time(f) for f in images}
    use_exif = bool(images) and not pdfs and all(times.values())
    if use_exif:
        ordered = sorted(images, key=lambda f: (times[f], natural_key(f.name)))
    else:
        ordered = sorted(images + pdfs, key=lambda f: natural_key(f.name))

    sources = []  # (원본 경로, PDF 쪽 번호 또는 None)
    for f in ordered:
        if f.suffix.lower() == ".pdf":
            import pymupdf
            with pymupdf.open(f) as doc:
                sources += [(f, i) for i in range(doc.page_count)]
        else:
            sources.append((f, None))
    return sources, ("EXIF 촬영 시각" if use_exif else "파일명 번호"), skipped


def source_key(code, src, page):
    return f"{code}/{src.name}" + (f"#{page + 1}" if page is not None else "")


def main():
    books = json.loads((ROOT / "data" / "books.json").read_text(encoding="utf-8"))
    codes = sys.argv[1:] or [b["code"] for b in books]
    known = {b["code"] for b in books}
    for d in RAW.iterdir():
        if d.is_dir() and d.name not in known:
            print(f"(건너뜀: scans/raw/{d.name}/ 는 books.json에 없는 폴더)")
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8")) if OVERRIDES.exists() else {}

    OUT.mkdir(parents=True, exist_ok=True)
    man_path = OUT / "manifest.json"
    manifest = json.loads(man_path.read_text(encoding="utf-8")) if man_path.exists() else {}

    for code in codes:
        sources, order_by, skipped = plan_book(code)
        # 재촬영본: 원본 자리(순서·쪽 번호)는 그대로 두고 읽는 파일만 바꾼다
        actual = {}
        for s, p in sources:
            rw = overrides.get(source_key(code, s, p), {}).get("replace_with")
            actual[(s, p)] = (RAW / rw, None) if rw else (s, p)
        jobs = [(source_key(code, s, p), str(actual[(s, p)][0]), actual[(s, p)][1],
                 overrides.get(source_key(code, s, p), {})) for s, p in sources]
        with ProcessPoolExecutor() as pool:
            decisions = list(pool.map(analyze, jobs, chunksize=4))

        render_jobs, entries, failed, n = [], {}, [], 0
        for (s, p), d in zip(sources, decisions):
            if "error" in d:
                failed.append(f"{d['key']} → {d['error']}")
                continue
            if d["split"]:
                halves = [("L", (0.0, d["l_end"])), ("R", (d["r_start"], 1.0))]
            else:
                halves = [(None, (0.0, 1.0))]
            crops = []
            for half, box in halves:
                n += 1
                name = f"{code}-p{n:04d}"
                crops.append((box, str(OUT / f"{name}.jpg")))
                src, src_page = actual[(s, p)]
                entries[name] = {"source": src.relative_to(ROOT).as_posix(), "pdf_page": src_page,
                                 "rotate": d["rotate"], "half": half,
                                 "crop": [round(box[0], 3), round(box[1], 3)]}
                if src != s:
                    entries[name]["replaces"] = s.relative_to(ROOT).as_posix()
            render_jobs.append((str(src), src_page, d["rotate"], crops))

        with ProcessPoolExecutor() as pool:
            failed += [e for e in pool.map(render, render_jobs, chunksize=4) if e]

        # 이전 실행에서 남은, 이번 번호 범위를 넘는 파일 (지우지 않고 알리기만)
        stale = sorted(p.name for p in OUT.glob(f"{code}-p*.jpg") if int(p.stem.split("-p")[1]) > n)

        manifest = {k: v for k, v in manifest.items() if not k.startswith(f"{code}-")}
        manifest.update(entries)
        ok = [d for d in decisions if "error" not in d]
        upright = [d["key"] for d in ok if d["rotate"] == 0]
        singles = [d["key"] for d in ok if not d["split"]]
        gutters = [d["split_at"] for d in ok if d["split"]]
        wide = [d for d in ok if d.get("gutter") == "all_differ"]

        print(f"[{code}] 원본 {len(sources)}장 → 쪽 이미지 {n}장 "
              f"(scans/prepared/{code}-p0001.jpg ~ {code}-p{n:04d}.jpg, 순서 기준: {order_by})")
        print(f"  돌리지 않음: {upright or '없음'}")
        print(f"  나누지 않은 한 쪽짜리: {singles or '없음'}")
        if gutters:
            print(f"  접힌 곳 위치: {min(gutters):.3f}~{max(gutters):.3f} (너비 대비)")
        if wide:
            widths = sorted(d["l_end"] - d["r_start"] for d in wide)
            print(f"  접힌 곳 후보 셋이 다 달라 넓게 겹쳐 나눔(확인 필요): {len(wide)}장 "
                  f"(겹침 폭 {widths[0]:.2f}~{widths[-1]:.2f}) {[d['key'] for d in wide]}")
        overridden = [d["key"] for d in ok if d["overridden"]]
        if overridden:
            print(f"  수동 지정 적용: {overridden}")
        print(f"  변환 실패: {failed or '없음'}")
        if skipped:
            print(f"  지원하지 않는 형식이라 건너뜀: {skipped}")
        if stale:
            print(f"  이전 실행에서 남은 파일(확인 필요): {stale[:5]}{' …' if len(stale) > 5 else ''} ({len(stale)}개)")

        # 검수용: 원본별 결정 기록
        (OUT / f"_decisions-{code}.json").write_text(
            json.dumps(decisions, ensure_ascii=False, indent=1), encoding="utf-8")

    man_path.write_text(json.dumps(dict(sorted(manifest.items())), ensure_ascii=False, indent=1),
                        encoding="utf-8")


if __name__ == "__main__":
    main()
