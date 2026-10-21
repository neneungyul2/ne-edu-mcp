# ne-edu-open-api-mcp

교육 공공데이터 두 곳을 묶은 MCP(Model Context Protocol) 서버입니다.

- **NEIS 교육정보 개방 포털**(open.neis.go.kr): 전국 **학원·교습소** 정보 (이름, 구분, 등록상태, 분야·교습과정, 과목별 교습비, 정원, 주소, 전화번호)
- **학교알리미**(schoolinfo.go.kr): 학교별 **공시정보** 35종 (학교 기본정보, 학생수, 교원, 급식, 방과후학교, 교복 단가 등)

결과는 대화에서 바로 조회하거나, 엑셀(xlsx)과 CSV로 저장할 수 있습니다.

## 도구 (9개)

| 구분 | 도구 | 인증키 |
|---|---|---|
| NEIS 학원·교습소 | `list_education_offices` (시도교육청 코드) | 불필요 |
| | `search_academies` (검색) | 권장* |
| | `get_academy` (학원지정번호로 1곳) | 권장* |
| | `export_academies` (xlsx/CSV 저장) | 필수 |
| 학교알리미 | `list_school_disclosure_items` (공시 항목 35종과 apiType) | 불필요 |
| | `describe_school_disclosure_item` (항목의 출력 필드) | 불필요 |
| | `list_school_regions` (시도·시군구·학교급 코드) | 불필요 |
| | `get_school_disclosure` (공시정보 조회) | 필수 |
| | `export_school_disclosure` (xlsx/CSV 저장) | 필수 |

\* NEIS는 인증키 없이도 응답하지만 **요청당 5건**만 줍니다. 키가 있으면 요청당 최대 1000건이고, 도구가 알아서 이어서 가져옵니다.

### 사용 예

- "서울 강남구 영어 학원 중 교습소만 찾아줘" → `search_academies(office="서울", zone="강남구", name="영어", kind="교습소")`
- "경기도 성남시 영어 학원 전부 엑셀로" → `export_academies`
- "서울 종로구 초등학교 전화번호와 홈페이지" → `get_school_disclosure(item="학교기본정보", sido="서울", sgg="종로구", school_kind="초등", fields=["전화번호", "홈페이지 주소"])`
- "경기도 중학교 교복 단가를 엑셀로" → `export_school_disclosure(item="교복 구매 유형 및 단가", sido="경기", school_kinds=["중학교"])`

### NEIS 조회 조건

서버가 거르는 조건: 시도교육청(필수), 행정구역(`zone`, 정확히 일치), 이름(`name`, 포함), 분야(`field`), 교습계열(`course_order`), 교습과정(`course`). 서버가 걸러주지 못하는 **구분(학원/교습소)·등록상태·교습과정목록**은 도구가 훑어서 거릅니다(최대 1만 건). 범위가 넓으면 결과에 `note`로 알려 주니 `zone`이나 `name`으로 먼저 좁히세요.

### 학교알리미 참고

- 공시 항목은 apiType 번호로 구분합니다(예: 학교기본정보 `0`, 학교 현황 `62`, 성별 학생수 `63`). `list_school_disclosure_items`로 찾으세요.
- 시도(`sido`)는 필수, 시군구를 비우면 시도 안 전체 시군구를 호출합니다(호출 수가 많아지니 학교명이나 시군구로 좁히면 빠릅니다).
- 광주와 전남은 공식 코드표에서 **전남광주통합특별시(12)** 로 합쳐져 있어 `광주`, `전남` 모두 12로 해석합니다.
- 학교알리미는 최근 3년 자료만 공시합니다. 데이터 출처 표시가 필요합니다(공공누리 출처표시).
- 항목·지역 카탈로그와 호출 형식은 학교알리미 공식 개발자 가이드와 출력값 엑셀로 만들었습니다. **실제 응답은 이 저장소 개발 시점에 인증키가 없어 확인하지 못했고**, 테스트는 가이드에 나온 응답 형식(`resultCode`, `resultMsg`, `list`)의 가짜 응답으로 했습니다. 키를 받은 뒤 한 번 실제 호출로 확인하세요.

## 설치

필요한 것: [uv](https://docs.astral.sh/uv/) (파이썬은 uv가 알아서 준비합니다)와 인증키.

- NEIS 인증키 (`NEIS_API_KEY`): https://open.neis.go.kr 에서 신청
- 학교알리미 인증키 (`SCHOOLINFO_API_KEY`): https://www.schoolinfo.go.kr > OpenAPI > API 이용안내 (네이버·카카오 로그인 후 발급)

### Windows + Claude Desktop (권장: 미리 설치)

`uvx --from git+...`로 실행 때마다 받으면, Claude Desktop이 서버를 여러 번 동시에 띄울 때 uv 캐시 쓰기가 겹쳐 시작에 실패할 수 있습니다. 터미널(Claude 밖)에서 한 번 설치하고 실행 파일을 직접 가리키세요.

```
uv tool install --force "git+https://github.com/neneungyul2/ne-edu-mcp"
```

`%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ne-edu-open-api": {
      "command": "C:\\Users\\내이름\\.local\\bin\\ne-edu-open-api-mcp.exe",
      "args": [],
      "env": {
        "NEIS_API_KEY": "발급Key",
        "SCHOOLINFO_API_KEY": "발급Key",
        "NEIS_EXPORT_DIR": "C:\\Users\\내이름\\Documents\\edu-exports"
      }
    }
  }
}
```

앱을 완전히 종료했다가 다시 실행합니다. 업데이트는 Claude를 종료한 뒤 위 `uv tool install --force` 명령을 다시 실행합니다.

### Claude Code

```
claude mcp add ne-edu-open-api -s user ^
  -e NEIS_API_KEY=발급Key -e SCHOOLINFO_API_KEY=발급Key ^
  -e NEIS_EXPORT_DIR=C:\Users\내이름\Documents\edu-exports ^
  -- C:\Users\내이름\.local\bin\ne-edu-open-api-mcp.exe
```

(줄 끝 `^`는 Windows cmd의 줄 이음입니다. PowerShell은 `` ` ``, macOS/Linux는 `\`를 쓰세요.)

### 환경변수

| 이름 | 설명 | 기본값 |
|---|---|---|
| `NEIS_API_KEY` | NEIS 인증키 (없으면 요청당 5건) | — |
| `SCHOOLINFO_API_KEY` | 학교알리미 인증키 (없으면 학교알리미 조회·내보내기 불가) | — |
| `NEIS_EXPORT_DIR` | 엑셀/CSV 저장 폴더. **지정을 권장합니다**(MCP 클라이언트가 서버를 실행하는 작업 폴더를 알 수 없어서) | `<작업 폴더>/exports` |
| `NEIS_CACHE_DIR` | API 응답 캐시 폴더 (인증키는 저장하지 않음) | `<홈>/.ne-edu-open-api-mcp/cache` |
| `NEIS_CACHE_TTL_HOURS` | 캐시 유지 시간(시간) | `24` |
| `NEIS_TOOLS_ALLOW` | 노출할 도구 이름(쉼표 구분, 비우면 전체) | 전체 |

환경변수가 비어 있는 키는 **작업 폴더의 `.env`**(`KEY=VALUE` 형식, `.env.example` 참고)에서 채웁니다.

## 개발

```
uv sync
uv run pytest
```

- `scripts/build_schoolinfo_data.py`: 학교알리미 공식 엑셀(`OpenAPI_Output.xlsx`, `sido_sggCode.xlsx`, https://www.schoolinfo.go.kr/download/)에서 `src/ne_edu_open_api_mcp/data/*.json`을 다시 만듭니다. 항목이 바뀌면 다시 실행하세요.
- 구조: `client.py`(NEIS) · `schoolinfo.py`(학교알리미 클라이언트·카탈로그) · `academy.py`·`school_service.py`(조회 서비스) · `tools/`(MCP 도구) · `export.py`·`cache.py`.

## 출처

- 학원·교습소: 교육부 나이스 교육정보 개방 포털 (https://open.neis.go.kr)
- 학교 공시정보: 한국교육학술정보원 학교알리미 (https://www.schoolinfo.go.kr), 공공누리 출처표시 이용허락
