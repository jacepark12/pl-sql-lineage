# Oracle PL/SQL Lineage

컬럼 레벨 리니지 엔진을 만들고 검증하기 위한 작업 공간입니다. 현재 저장소에는
**Python 리니지 엔진**, **합성 코퍼스 생성기**, **브라우저 리니지 뷰어**,
**설계·조사 문서**가 있습니다.

엔진은 Oracle PL/SQL 패키지에서 컬럼 단위 엣지를 뽑고, 코퍼스 정답셋으로 채점합니다.
뷰어는 그 결과를 그리는 별도 계약(`objects` / `relationships`)을 읽습니다.

> 초기 MVP였던 Java 분석기(`src/main/java/io/sqlflowmvp`)와 Gradle 빌드는 커밋
> `9dff998`에서 제거되었습니다. 지금은 Python 엔진(`plsql-lineage-engine/`)이
> 그 자리를 차지합니다. 당시 구현에 대한 기록은 아래
> [제거된 MVP 분석기](#제거된-mvp-분석기)에만 남아 있습니다.

## 구성

| 경로 | 내용 |
|---|---|
| `plsql-lineage-engine/` | Python 컬럼 리니지 엔진. ANTLR PL/SQL 파서 + sqlglot 문장 분석 + 변수 데이터플로 |
| `plsql-lineage-corpus/` | 합성 PL/SQL + webMethods EAI 코퍼스와 리니지 정답셋 생성기 (Python, 무의존성) |
| `web/index.html` | 서버 없이 열리는 단일 파일 리니지 뷰어 |
| `scripts/generate_lineage_scale_sample.py` | 뷰어 스케일 점검용 대용량 리니지 JSON 생성기 |
| `docs/` | 엔진 로드맵·아키텍처, OpenMetadata 조사, 저장 스키마 설계 |

흐름은 한 방향입니다.

```
코퍼스 생성 (SQL + 정답셋)  →  엔진 실행 (edges JSON)  →  synplsql.score
                                                      ↘  plsqllineage.export → 뷰어 JSON
```

## 리니지 엔진

`plsql-lineage-engine/` 이 SQL을 실제로 분석합니다. 파서는 생성물이라 커밋되어 있지
않으므로 최초 1회 빌드합니다. 자세한 준비·성능은
[plsql-lineage-engine/README.md](plsql-lineage-engine/README.md)에 있습니다.

```sh
cd plsql-lineage-engine
pip install -r <(python3 -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))")
python3 scripts/build_parser.py      # java 필요. 10초 내외

# 코퍼스 루트를 넘깁니다. packages/ 만 넘기면 location.file 이 정답셋과 어긋납니다.
python3 -m plsqllineage.engine \
  --input ../plsql-lineage-corpus/out/dev \
  --out /tmp/engine.json
```

`--input` 이 코퍼스 루트이면 `packages/*.sql` 만 분석하고 `ddl/catalog.sql` 은
`SELECT *` 전개용 카탈로그로 읽습니다.

### 지금 되는 것 / 아직 안 되는 것

[docs/engine-roadmap.md](docs/engine-roadmap.md) 기준입니다.

| | 상태 |
|---|---|
| PL/SQL 구조 추출 (패키지·프로시저·문장) | 됨 |
| `INSERT` / `UPDATE` / `DELETE` / `SELECT INTO` / `INSERT ... VALUES` | 됨 |
| 문장 간 변수 데이터플로 (`VIA_VARIABLE`) | 됨 |
| `MERGE` (MATCHED UPDATE + NOT MATCHED INSERT + ON 필터) | 됨 |
| CTE / 인라인 뷰 관통 (`VIA_CTE`, 원천 테이블까지) | 됨 |
| `SELECT *` / `alias.*` (DDL 카탈로그 필요) | 됨 |
| Tier 0~1 합성 코퍼스 | 엣지 F1 100%, 다홉 103/103 |
| Tier 2 합성 코퍼스 (`MERGE` / CTE / `SELECT *`) | 엣지 F1 100%, 다홉 221/221 |
| 동적 SQL (`EXECUTE IMMEDIATE`) | 지어내지 않아야 함. 아직 진단으로 안 남김 |
| DB link (`table@LINK`) | 미지원 |
| 엔진 JSON → 뷰어 `objects`/`relationships` | `plsqllineage.export` / `--format viewer` |

Tier 0~1 의 100% 는 "엔진 완성"이 아닙니다. 그 구간의 천장이 원래 100% 입니다.

## 합성 코퍼스 생성기

실제 자산의 구문 분포를 재현하되 업무 내용은 전부 가상입니다. 소스 SQL과 리니지 정답을 같은
중간표현에서 동시에 파생시키므로 라벨링 오류가 원천적으로 없습니다.

| 계층 | 대상 | 규모 (seed 20260812) |
|---|---|---|
| PL/SQL | Oracle 패키지 | 201 패키지 / 300,612 라인 / 엣지 8,629 |
| EAI | webMethods 인터페이스 | 40 인터페이스 / 아티팩트 486 / 엣지 488 |

두 계층은 인터페이스 테이블에서 접합되어 원천 시스템 → EAI → 인터페이스 테이블 → PL/SQL →
리포트로 이어지는 **15홉 리니지 체인**을 만듭니다.

```sh
cd plsql-lineage-corpus

# PL/SQL 코퍼스 (5초 내외)
python3 -m synplsql.generate --out out --stats
python3 -m synplsql.validate --out out

# EAI 코퍼스 + 두 계층 정답셋 병합
python3 -m syneai.generate --out out/eai --merge out --stats
python3 -m syneai.validate --out out/eai
```

산출물은 `out/` 아래에 생성되며 `.gitignore` 대상입니다.

| 경로 | 내용 |
|---|---|
| `out/ddl/catalog.sql` | 가상 스키마 DDL. `SELECT *` 전개와 `%TYPE` 해소에 필요 |
| `out/packages/*.sql` | 패키지 소스 (스펙 + 바디) |
| `out/lineage_truth.json` | 리니지 정답셋. 엣지별 종류·변환식·파일/프로시저/라인 |
| `out/manifest.json` | 패키지별 티어·라인 수·시나리오, 최장 리니지 체인 |
| `out/lineage_truth_merged.json` | PL/SQL + EAI 통합 정답셋 (`--merge` 사용 시) |

인터프리터는 **3.11 이상**이 필요합니다(`core.py`의 `X | Y` 타입 문법). 개발 기준 버전은
`.python-version`의 `3.12`이며, [uv](https://docs.astral.sh/uv/)를 쓰면 자동으로 맞춥니다.

리니지 엔진의 출력은 정답셋 대비로 채점합니다.

```sh
python3 -m synplsql.score \
  --truth out/dev/lineage_truth.json \
  --manifest out/dev/manifest.json \
  --engine /tmp/engine.json \
  --format generic
```

엣지 P/R/F1, kind 정확도, Tier별 지표, 다홉 완주율을 냅니다. 자세한 설계·티어 구성·채점
기준은 [plsql-lineage-corpus/README.md](plsql-lineage-corpus/README.md)에 있습니다.

## 리니지 뷰어

```sh
open web/index.html
```

빌드도 서버도 필요 없는 단일 HTML 파일입니다. 내장 데모가 첫 화면에 바로 뜨고, 왼쪽
`Explorer`의 `Open JSON`으로 분석기 출력을 올리면 실제 결과로 교체됩니다.
엔진 `edges` JSON 은 먼저 뷰어 계약으로 바꿉니다.

```sh
cd plsql-lineage-engine
python3 -m plsqllineage.export --input /tmp/engine.json --out /tmp/viewer.json
# 또는 엔진에서 바로:  --out /tmp/viewer.json --format viewer
```

매핑 표는 [plsql-lineage-engine/README.md](plsql-lineage-engine/README.md#뷰어-exporter)에 있습니다.

3패널 구성입니다.

- **Explorer** — 객체 트리, 이름 검색, 관계 유형 필터(`direct` / `indirect` / `call` / `dynamic_sql`)
- **Graph** — 테이블·뷰를 노드로, 컬럼을 노드 내부 행으로 배치하고 엣지를 해당 행에 연결.
  프로시저·함수는 매개변수를 행으로 가집니다. `Objects` / `Relationships` / `Diagnostics`
  탭으로도 같은 데이터를 표로 볼 수 있습니다.
- **Inspector** — 선택한 객체의 소유 객체, 멤버, 입력/출력 관계와 변환 표현식

그래프 캔버스에서 지원하는 조작:

- 빈 공간 드래그로 자유 팬, `Ctrl`/`⌘` + 휠로 포인터 기준 줌, 더블클릭으로 전체 맞춤
- `Fit` / `Reset` / `Focus selection`, 줌 배율 표시와 `+` `−` 버튼
- 노드 드래그 배치, 우클릭 컨텍스트 메뉴(상세 보기, 노드 중앙 정렬, 연결 리니지 집중,
  업스트림/다운스트림 보기, 객체 ID 복사)
- 리니지 범위 선택(전체 / 선택 기준 업스트림 / 다운스트림 / 연결된 것만), `Linked columns only` 토글
- 우하단 미니맵으로 위치 파악과 이동
- 뷰포트 컬링. 화면에 들어오는 노드·엣지만 그리며 현재 렌더 수를 툴바에 표시합니다

### 뷰어가 읽는 JSON 계약

```json
{
  "objects":       [{ "id": "column.orders.order_amount", "type": "column", "name": "ORDERS.ORDER_AMOUNT" }],
  "relationships": [{ "type": "direct", "source": "<id>", "target": "<id>", "expression": "SUM(o.order_amount)" }],
  "diagnostics":   []
}
```

- `objects[].type`: `table`, `view`, `column`, `package`, `procedure`, `function`, `parameter`, `trigger`, 동적 SQL 문장
- `relationships[].type`: `direct`, `indirect`, `call`, `dynamic_sql`
- 컬럼과 매개변수는 ID 접두사(`column.<table>.<column>`)로 소유 객체에 묶여 노드 내부 행이 됩니다

### 스케일 점검

노드 수가 늘었을 때 뷰어가 버티는지 확인하려면 결정적 대용량 샘플을 만들어 올립니다.

```sh
python3 scripts/generate_lineage_scale_sample.py --nodes 1000 --out reports/demo/lineage-scale-1000.json
```

뷰어의 `Load 1,000 demo` 버튼은 같은 형태의 1,000노드 체인을 파일 없이 즉시 로드합니다.

## 문서

| 문서 | 내용 |
|---|---|
| [docs/openmetadata-column-lineage.md](docs/openmetadata-column-lineage.md) | OpenMetadata 컬럼 리니지 조사. JSON Schema 타입 카탈로그, sqlglot → collate-sqllineage 의존성 체인 |
| [docs/openmetadata-lineage-schema.html](docs/openmetadata-lineage-schema.html) | 위 스키마의 타입 참조와 다이어그램 (브라우저로 열기) |
| [docs/validation-limits.md](docs/validation-limits.md) | **검증의 한계**. 합성 코퍼스가 보장하는 것과 보장하지 않는 것, 실무 코드로 무엇을 잴 수 있는지 |
| [docs/engine-roadmap.md](docs/engine-roadmap.md) | 엔진 **구현 현황과 남은 작업**. 지금 어디까지 됐고 무엇이 검증되지 않았는지 |
| [docs/engine-architecture.md](docs/engine-architecture.md) | 리니지 엔진 **설계 기록**. 난이도 티어, 3계층 구조, 그 근거가 된 측정. 구현 현황은 로드맵을 보십시오 |
| [docs/column-lineage-schema.md](docs/column-lineage-schema.md) | 컬럼 계보 **저장 스키마 설계안**. 무엇을 영속화하고 무엇을 캐시로 둘지, 테이블 3개와 마이그레이션 |
| [docs/column-lineage-for-agents.md](docs/column-lineage-for-agents.md) | AI 에이전트가 읽고 쓰는 대상으로서의 스키마 평가. 컬럼 매핑이 addressable 하지 않다는 설계 결정과 그 파급 |
| [plsql-lineage-corpus/docs/PLAN.md](plsql-lineage-corpus/docs/PLAN.md) | PL/SQL 생성기 설계와 난이도 티어 |
| [plsql-lineage-corpus/docs/PLAN-EAI.md](plsql-lineage-corpus/docs/PLAN-EAI.md) | EAI 생성기 설계 |
| [plsql-lineage-corpus/docs/WM-VALUES-FORMAT.md](plsql-lineage-corpus/docs/WM-VALUES-FORMAT.md) | webMethods 값 블롭 포맷 분석 |

## 제거된 MVP 분석기

Java로 작성한 초기 분석기는 커밋 `9dff998`에서 제거되었습니다. 함께 삭제된 것은 Gradle
빌드, 골든/공개/파서 픽스처, 생성된 코퍼스 산출물, `reports/demo/`입니다.

당시 기준선은 합성 PL/SQL 코퍼스에서 엣지 F1 70.7%, 다홉 완주율 23.6%였고 EAI 계층은
지원 범위 밖이었습니다. `synplsql.score`의 `--format sqlflow-mvp` 옵션은 그 분석기의 JSON
계약을 읽기 위한 것으로, 뷰어가 읽는 계약과 같습니다. 현재 엔진은 `--format generic`
(정답셋과 같은 `edges` 형식)으로 채점합니다.

설계 의도와 한계는 아래 기록에 남아 있습니다. 현재 저장소 상태를 설명하는 문서가 아니라,
제거된 구현에 대한 기록입니다. 현재 엔진의 지원 범위는
[docs/engine-roadmap.md](docs/engine-roadmap.md)를 보십시오.

- [docs/mvp-implementation.md](docs/mvp-implementation.md) — 분석 파이프라인, 검증 기준, 의도적 한계
- [docs/test-corpus.md](docs/test-corpus.md) — 당시 사용하던 공개 테스트 SQL의 출처와 고정 커밋
