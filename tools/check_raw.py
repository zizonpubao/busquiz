"""scans/raw/<책코드>/ 사진의 장 수, 번호 범위, 빠진 번호, 열리지 않는 파일을 확인한다.

파일명이 "... - N.jpg" 꼴(아이폰/드라이브 내보내기)이라고 가정한다.
사용: python tools/check_raw.py
"""
import re, sys
from pathlib import Path
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent / "scans" / "raw"
NUM = re.compile(r"- (\d+)\.\w+$")

for book_dir in sorted(p for p in ROOT.iterdir() if p.is_dir()):
    files = sorted(f for f in book_dir.iterdir() if f.is_file())
    nums, odd, broken = [], [], []
    for f in files:
        m = NUM.search(f.name)
        (nums.append(int(m.group(1))) if m else odd.append(f.name))
        try:
            with Image.open(f) as im:
                im.verify()
        except Exception as e:
            broken.append(f"{f.name}: {e}")
    nums.sort()
    dupes = sorted({n for n in nums if nums.count(n) > 1})
    missing = sorted(set(range(1, nums[-1] + 1)) - set(nums)) if nums else []
    mb = sum(f.stat().st_size for f in files) / 1e6
    print(f"[{book_dir.name}] {len(files)}장, {mb:.0f}MB, 번호 1~{nums[-1] if nums else '-'}")
    print(f"  빠진 번호: {missing or '없음'}")
    if dupes:
        print(f"  중복 번호: {dupes}")
    if odd:
        print(f"  이름 형식이 다른 파일: {odd}")
    if broken:
        print(f"  열리지 않는 파일: {broken}")
