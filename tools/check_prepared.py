"""prepare_images.py의 회전·쪽 나누기 결과를 눈으로 검수하는 썸네일 모음을 만든다.

원본을 결정대로 돌린 뒤, 왼쪽 쪽 끝(파랑)과 오른쪽 쪽 시작(초록)을 그려 한 장에 60개씩 모은다.
접힌 곳 후보가 서로 달라 넓게 겹친 사진은 이름표가 빨강.
결과: scans/prepared/_check/<책코드>-NN.jpg
사용: python tools/check_prepared.py [책코드 ...]
"""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
from prepare_images import OUT, ROOT, load  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
CHECK = OUT / "_check"
TW, TH, COLS, PER_SHEET = 300, 220, 6, 60


def thumb(d, raw_dir):
    name, _, page = d["key"].partition("/")[2].partition("#")
    im = load(raw_dir / name, int(page) - 1 if page else None)
    if d["rotate"]:
        im = im.rotate(d["rotate"], expand=True)
    im.thumbnail((TW - 6, TH - 22))
    dr = ImageDraw.Draw(im)
    if d["split"]:
        w, h = im.size
        # 파랑: 왼쪽 쪽의 오른쪽 끝, 초록: 오른쪽 쪽의 왼쪽 끝 (그 사이가 양쪽에 다 들어가는 겹침)
        for x, c in ((d["l_end"], "blue"), (d["r_start"], "green")):
            dr.line([(x * w, 0), (x * w, h)], fill=c, width=2)
    return im


def main():
    CHECK.mkdir(parents=True, exist_ok=True)
    codes = sys.argv[1:] or [p.stem.split("-", 1)[1] for p in OUT.glob("_decisions-*.json")]
    for code in codes:
        decisions = json.loads((OUT / f"_decisions-{code}.json").read_text(encoding="utf-8"))
        decisions = [d for d in decisions if "error" not in d]
        for s in range(0, len(decisions), PER_SHEET):
            chunk = decisions[s:s + PER_SHEET]
            rows = (len(chunk) + COLS - 1) // COLS
            sheet = Image.new("RGB", (COLS * TW, rows * TH), "white")
            dr = ImageDraw.Draw(sheet)
            for i, d in enumerate(chunk):
                x, y = (i % COLS) * TW, (i // COLS) * TH
                sheet.paste(thumb(d, ROOT / "scans" / "raw" / code), (x + 3, y + 20))
                label = d["key"].rsplit("- ", 1)[-1] + f"  r{d['rotate']}"
                label += f" @{d['split_at']:.2f} {d['gutter']}" if d["split"] else " single"
                dr.text((x + 3, y + 3), label, fill="red" if d.get("gutter") == "all_differ" else "blue")
            out = CHECK / f"{code}-{s // PER_SHEET + 1:02d}.jpg"
            sheet.save(out, quality=80)
            print(out.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
