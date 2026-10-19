# BusQuiz 배포·설치 (7단계)

## 올리는 것 / 안 올리는 것
- GitHub에 올리는 것: `app/`, `tools/`, `CLAUDE.md`, `.gitignore` 등 **문제가 들어 있지 않은 파일만**
- 절대 올리지 않는 것: `scans/`, `data/`, `packs/` (`.gitignore`에 있음). 올리기 전에 `git status`로 확인

## GitHub Pages
1. 저장소 만들기(private 가능) → `git add -A && git commit` → `git push`. 올리기 전에 `git status`에 `data/`·`packs/`·`scans/`가 없는지 본다
2. 공개 폴더 정하기 — 둘 중 하나:
   - (권장) `app/`를 `docs/`로 복사해서 함께 커밋하고, 저장소 Settings → Pages → Source: *Deploy from a branch*, Branch `main`, Folder **`/docs`**
     ```bash
     rm -rf docs && cp -r app docs
     ```
   - 또는 GitHub Actions: Pages Source를 *GitHub Actions*로 두고 `actions/upload-pages-artifact`에 `path: app`
3. 주소: **https://zizonpubao.github.io/busquiz/** (저장소 zizonpubao/busquiz, GitHub Actions 방식으로 배포 중. sw.js·manifest는 상대 경로라 하위 경로에서도 동작)
   - 배포 확인(2026-10-19): index.html·sw.js·manifest·js·css 200, `data/`·`packs/`·`scans/` 404
4. 앱을 고친 뒤에는 `app/sw.js`의 `VERSION`을 올리고(`busquiz-v2` …) 다시 push. 폰에서 앱을 두 번 열면 새 버전이 적용된다

## 아이폰 설치
1. 문제팩 `packs/busquiz-gs.json`, `packs/busquiz-jc.json`을 iCloud Drive(파일 앱) 폴더에 넣는다 (AirDrop도 가능)
2. Safari로 https://zizonpubao.github.io/busquiz/ 열기 → 공유 → **홈 화면에 추가**
3. 홈 화면 아이콘으로 열고 → "문제팩 불러오기" → 파일 앱에서 json 선택 (책마다 한 번)
4. 이후엔 인터넷 없이 동작. 문제팩을 새로 만들면 설정 → 문제팩 불러오기로 같은 책을 다시 선택하면 된다 (학습 기록 유지)
5. 학습 기록은 설정 → 백업 내보내기(JSON)로 파일 앱에 저장해 둔다

## 로컬 확인
```bash
python -m http.server 8765 --bind 127.0.0.1
```
→ `http://127.0.0.1:8765/app/`
