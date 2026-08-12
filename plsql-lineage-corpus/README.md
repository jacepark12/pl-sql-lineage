# 합성 리니지 코퍼스 생성기

컬럼 레벨 리니지 엔진의 개발·검증에 쓰는 **합성 코퍼스**와 **리니지 정답셋**을 생성한다.
두 계층으로 이루어져 있고, 인터페이스 테이블에서 서로 접합된다.

| 계층 | 생성기 | 대상 | 설계 문서 |
|---|---|---|---|
| DB 내부 | `synplsql/` | Oracle PL/SQL 패키지 | [docs/PLAN.md](docs/PLAN.md) |
| 시스템 간 | `syneai/` | webMethods EAI 패키지 | [docs/PLAN-EAI.md](docs/PLAN-EAI.md) |

```
SYNSRC.SRC_ITEM_MST ─EAI─▶ SYNIF.IF_ITEM_RCV ─PL/SQL─▶ SYNWMS.MST_ITEM ─▶ … ─▶ RPT_DAILY_STK
   원천 시스템                 인터페이스 테이블              업무 DB                리포트
```

EAI 계층이 없으면 리니지 그래프는 인터페이스 테이블에서 끊긴다. "이 리포트 값이 원래
어느 시스템에서 왔나"는 그 구간을 넘어야 답할 수 있는 질문이다.

핵심은 하나다 — **정답에서 코드를 역생성한다.** 동일한 중간표현(IR)에서 SQL 텍스트와
리니지 정답을 동시에 파생시키므로 라벨링 비용이 0이고, 정답에 오류가 섞일 여지가 없다.

```
profile.json ─┐
schema.py ────┼─▶ scenarios.py ─▶ [IR 문장 트리] ─┬─▶ core.render()  ─▶ *.sql
seed ─────────┘                                    └─▶ core.edges()   ─▶ lineage_truth.json
```

## 바로 실행하기

```sh
cd plsql-lineage-corpus

# PL/SQL 코퍼스 (200 패키지 / 30만 라인, 4초 내외)
python3 -m synplsql.generate --out out --stats
python3 -m synplsql.validate --out out

# EAI 코퍼스 + 두 계층 정답셋 병합
python3 -m syneai.generate --out out/eai --merge out --stats
python3 -m syneai.validate --out out/eai

# 개발 초기에는 쉬운 티어만 빠르게
python3 -m synplsql.generate --tier 0,1 --packages 20 --lines 30000 --out out/dev

# 엔진 출력 채점
python3 -m synplsql.score --engine <엔진출력.json> --format sqlflow-mvp --ignore-schema
```

의존성은 없다. Python 3.11 이상 표준 라이브러리만 사용한다.

## 산출물

| 경로 | 내용 |
|---|---|
| `out/ddl/catalog.sql` | 가상 스키마 DDL. `SELECT *` 전개와 `%TYPE` 해소에 필요 |
| `out/packages/*.sql` | 패키지 소스 (스펙 + 바디) |
| `out/lineage_truth.json` | 리니지 정답셋. 엣지별 종류·변환식·파일/프로시저/라인 |
| `out/manifest.json` | 패키지별 티어·라인 수·시나리오, 최장 리니지 체인 |

`out/` 은 `.gitignore` 대상이다. 커밋된 `samples/`(PL/SQL 6패키지)와 `samples-eai/`
(EAI 3인터페이스)에 생성 예시가 들어 있으므로, 실행 없이도 산출물의 형태를 확인할 수 있다.

## 기본 코퍼스 (seed 20260812)

| 지표 | PL/SQL | EAI |
|---|---:|---:|
| 단위 | 패키지 201 | 인터페이스 40 |
| 규모 | 300,612 라인 | 아티팩트 486 / 어댑터 86 |
| 서브프로그램 | 프로시저 563 / 함수 95 | FLOW 서비스 120 |
| 리니지 엣지 | 8,629 | 488 |
| 최대 단위 | 32,655 라인 | — |
| 통합 최장 체인 | 15홉 (원천 시스템 → 리포트) | |

엣지 종류 분포:

| 종류 | 건수 | 의미 |
|---|---:|---|
| `DIRECT` | 2,890 | 단순 컬럼 대입 |
| `TRANSFORM` | 1,485 | 함수·연산 경유 |
| `AGGREGATE` | 70 | 집계함수. 여러 행이 한 값으로 접힘 |
| `ANALYTIC` | 161 | 분석함수 (PARTITION/ORDER 컬럼 포함) |
| `VIA_CTE` | 464 | CTE·인라인 뷰 경유 (전이 해석 필요) |
| `VIA_VARIABLE` | 545 | PL/SQL 변수·커서 레코드·컬렉션 경유 |
| `INDIRECT_FILTER` | 2,888 | WHERE / JOIN / GROUP BY / CASE 조건절 |
| `UNRESOLVED` | 126 | 동적 SQL. 정적 해석 불가 |

EAI 계층은 여기에 3종을 더한다.

| 종류 | 건수 | 의미 |
|---|---:|---|
| `VIA_PIPELINE` | 161 | webMethods 파이프라인 경유 |
| `TRANSFORM` | 86 | MAPINVOKE 변환기 / 어댑터 `update.expression` |
| `CONSTANT` | 131 | MAPSET 리터럴. 값은 들어가지만 원천 컬럼이 없음 |
| `SEVERED` | 77 | MAPDELETE / clearPipeline 으로 리니지가 여기서 끊김 |
| `INDIRECT_FILTER` | 27 | Select 어댑터 WHERE / 조건부 적재 |
| `UNRESOLVED` | 6 | CustomSQL. SQL 파서 필요 |

`SEVERED` 를 정답에 명시하는 이유는 `UNRESOLVED` 와 같다 — **"엔진이 못 찾은 것"과
"실제로 끊긴 것"을 구분해야 Recall 이 의미를 갖는다.** 매핑만 수집하는 엔진은 이 77건에
대해 원천이 있다고 답하고, 그것이 오답이다.

`INDIRECT_FILTER` 를 따로 분류하는 이유는 두 질의가 다르기 때문이다. "이 컬럼이 바뀌면
무엇이 영향받나"에는 필터 컬럼도 답에 포함되어야 하지만, "이 값이 어디서 왔나"에는
제외되어야 한다. 생성 시점부터 나눠 라벨링해야 두 질의를 구분해 채점할 수 있다.

## 실측 분포 재현

생성기 사양은 임의로 정하지 않았다. 실제 레거시 PL/SQL 자산 **390 패키지 / 612,825 라인**을
정적 분석해 얻은 구문 출현 통계를 `profile.json` 에 담고, 생성 시 쿼터로 강제한다.

> 코퍼스에 반영되는 것은 **"CASE WHEN이 1,000라인당 12.7회 출현한다"는 통계값**이며,
> 실제 코드 문자열·식별자·업무 로직은 일절 이식하지 않는다. 통계는 코드가 아니므로
> 반출 제약에 걸리지 않으면서 파서가 마주칠 난이도는 그대로 재현할 수 있다.

`--stats` 는 생성 결과를 실측 분포와 대조한다. 24개 구문과 6개 규모 지표 전부가
허용오차(상대 35%) 안에 들어야 `--strict` 가 0을 반환한다.

```
구문 프로파일 대조  (파일 201개 / 300,612 라인)
construct           target/1K  actual/1K    target   actual   판정
CASE_WHEN               12.66      12.63      3806     3798   OK
TYPE_ANCHOR             13.24      16.79      3980     5046   OK
UPDATE_SET               1.87       2.38       562      715   OK
INSERT_INTO              1.52       1.74       457      524   OK
REF_CURSOR               1.21       1.06       364      318   OK
...
```

쿼터는 자기 조정식이다. 각 구문의 남은 할당량에 비례해 시나리오를 뽑고, 모든 할당량이
소진되면 DML 없는 순수 제어흐름 프로시저를 만든다. 그래서 템플릿을 늘려도 분포가
무너지지 않는다.

## 난이도 티어

| Tier | 포함 구문 | 라인 비중 |
|---|---|---:|
| **0** | 단순 `INSERT ... SELECT`, 단일 테이블, 컬럼 1:1 | 15% |
| **1** | 다중 조인, `CASE`/`DECODE`/`NVL`, 상관 서브쿼리 `UPDATE` | 40% |
| **2** | `MERGE`, CTE, 집계/분석함수, `SELECT *`, `(+)` 조인, 변수 매개, DB 링크 | 35% |
| **3** | 커서 루프, `BULK COLLECT`, REF CURSOR, `CONNECT BY`, `PIVOT`, 동적 SQL | 10% |

티어는 **라인 수 기준**으로 배분된다. 패키지 개수로 나누면 특정 티어가 작은 패키지에만
몰려 실제 비중이 선언값과 어긋난다.

Tier 3 패키지는 의도적으로 구문 밀도가 높다. 코퍼스 전체의 하드 구문 할당량을
전체 라인의 10%인 Tier 3 안에서 채워야 하기 때문이다.

## 의도된 다단 리니지 체인

리니지 엔진의 진짜 시험대는 단일 문장이 아니라 다중 홉이다.

```
IF_ITEM_RCV ──▶ MST_ITEM ──┐
                            ├─▶ INB_RESULT ─▶ STK_ONHAND ─▶ STK_TRX ─▶ RPT_DAILY_STK
INB_ORDER_H/D ──────────────┘                     │
                                                  └─▶ OUT_ALLOC ─▶ OUT_PICK ─▶ OUT_SHIP ─▶ IF_ORDER_SND
```

`RPT_DAILY_STK.END_WGT` 에서 역추적해 `SYNIF.IF_ITEM_RCV.UNIT_WGT` 까지 도달하는지가
최종 검증 항목이다. `manifest.json` 의 `longest_chain` 이 생성된 코퍼스에서 실제로
가장 긴 체인을 보여준다.

## 정답셋 포맷

```json
{
  "target": { "table": "SYNWMS.STK_ONHAND", "column": "ONHAND_QTY" },
  "sources": [ { "table": "SYNWMS.INB_RESULT", "column": "RCV_QTY" } ],
  "kind": "TRANSFORM",
  "transform": "NVL(r.RCV_QTY, 0)",
  "hops": 1,
  "via": ["CTE"],
  "location": {
    "file": "packages/SYNWMS.PKG_INB_002.sql",
    "package": "PKG_INB_002",
    "procedure": "SP_APPLY_INB_RESULT",
    "stmt_id": 3,
    "line": 128
  }
}
```

`location.line` 은 해당 엣지를 만든 **바로 그 줄**을 가리킨다. SELECT 항목 엣지는 그
항목 줄을, WHERE/JOIN 필터 엣지는 그 술어 줄을 가리킨다. 엔진이 틀렸을 때 어느 문장에서
틀렸는지 즉시 역추적할 수 있어야 디버깅 사이클이 돈다.

`via` 는 값이 거쳐 온 경로를 알려준다 — `CTE`(CTE·인라인 뷰), `VARIABLE`(PL/SQL 변수),
`DERIVED`(`MERGE ... USING` 투영). `DERIVED` 는 홉으로 세지 않지만, 바깥 표현식에는
원천 컬럼명이 나타나지 않는다는 사실을 알려준다.

## 자체 검증

`python3 -m synplsql.validate` 는 생성된 텍스트에서 재유도할 수 있는 것을 다시 유도해
정답셋과 대조한다. IR을 두 번 믿는 대신 렌더링 결과와 맞춰 보는 것이 요점이다.

- 모든 엣지의 라인 번호가 파일 범위 안이고, 기록된 프로시저 내부에 있는가
- 기록된 변환식이 그 라인 주변에 실제로 렌더링되어 있는가
- 엣지의 모든 원천 컬럼이 변환식에 등장하는가 — **별칭 오해소를 잡는 핵심 검사**
- 모든 테이블·컬럼이 DDL 카탈로그에 존재하는가
- 괄호·따옴표 균형, 패키지 바디 존재, 슬래시 종결
- 동일 seed → 동일 코퍼스 (재현성)

## 수작업 픽스처

`fixtures/` 에는 구문별 엣지케이스가 **손으로 쓴 SQL + 손으로 쓴 라벨**로 들어 있다.
생성된 정답셋은 스스로를 감사할 수 없다 — SQL과 라벨이 같은 IR에서 나오므로 IR의 버그는
안에서 보이지 않는다. 픽스처는 그 사각지대를 메운다.

| 픽스처 | 검증 대상 |
|---|---|
| `01_insert_select_direct` | 단순 1:1 대응 (스모크) |
| `02_case_decode_split` | CASE 조건부=INDIRECT, 결과부=TRANSFORM 분리 |
| `03_alias_resolution_trap` | 같은 컬럼명이 3개 테이블에 존재. 별칭 해소 강제 |
| `04_merge_both_branches` | MERGE의 UPDATE절/INSERT절 양방향 엣지 |
| `05_cte_transitive` | CTE 경유 전이 리니지 (hops=2) |
| `06_analytic_partition` | PARTITION BY / ORDER BY 컬럼도 원천 |
| `07_select_star_expansion` | DDL 카탈로그 없이는 해소 불가 |
| `08_legacy_outer_join` | 오라클 구식 `(+)` 외부조인 |
| `09_select_into_variable` | 변수 매개 리니지 |
| `10_cursor_loop_record` | 커서 → 레코드 → INSERT |
| `11_bulk_collect_forall` | 컬렉션 매개 리니지 |
| `12_connect_by_hierarchy` | 계층 쿼리 자기참조 |
| `13_dynamic_sql_unresolved` | UNRESOLVED가 정답 |
| `14_db_link_escape` | 외부 스키마로 리니지 유출 |
| `15_pivot_columns` | 행↔열 전환 (최난도) |
| `16_aggregate_group_rollup` | 최상위 집계와 GROUP BY 기준 컬럼 구분 |

`validate` 는 픽스처 라벨도 함께 검사하고, 생성기가 만드는 엣지 종류와 손으로 라벨링한
종류가 서로를 빠짐없이 덮는지 교차 확인한다.

## 채점

```sh
python3 -m synplsql.score --engine <출력.json> --format generic
python3 -m synplsql.score --engine <출력.json> --format sqlflow-mvp --ignore-schema
```

| 지표 | 정의 |
|---|---|
| 파싱 성공률 | 문법 오류 없이 파싱된 파일 비율 (엔진이 진단을 낼 때만) |
| 엣지 P / R / F1 | 고유 `source → target` 쌍 기준 |
| Kind 정확도 | 정밀(정확한 라벨) / 개략(값 흐름 vs 필터) 2단계 |
| Tier별 P/R/F1 | 엔진이 `location.file` 을 낼 때. 아니면 재현율만 |
| 다홉 완주율 | 2홉 이상 체인의 모든 링크를 찾았는가 |

동적 SQL(`UNRESOLVED`)은 P/R 계산에서 제외하고 별도 집계한다. 정적 해석이 원리적으로
불가능한 영역을 억지로 추적하려다 엔진 복잡도가 폭증하는 것을 막기 위해, 처음부터
"해석 불가"를 정상 출력으로 인정한다.

### 이 저장소 엔진의 기준선

`src/main/java/io/sqlflowmvp` 의 분석기를 기본 코퍼스에 투입한 결과다.

| 지표 | 값 |
|---|---:|
| 파싱 성공률 | 100.0% (201/201) |
| 엣지 Precision | 77.4% |
| 엣지 Recall | 65.1% |
| 엣지 F1 | 70.7% |
| Kind 정확도 (개략) | 56.7% |
| 다홉 완주율 | 23.6% |

문장 단위 정확도(F1 70.7%)에 비해 다홉 완주율이 3분의 1 수준으로 떨어지는 것이 눈에 띈다.
개별 엣지를 대체로 맞히더라도 체인 중간의 한 링크만 놓치면 끝까지 추적하는 질의는
실패하므로, 다홉 지표가 실사용 정확도에 더 가깝다.

재현 방법:

```sh
javac -d /tmp/classes src/main/java/io/sqlflowmvp/*.java
java -cp /tmp/classes io.sqlflowmvp.Main analyze \
  --input plsql-lineage-corpus/out/packages --out /tmp/engine.json
cd plsql-lineage-corpus && python3 -m synplsql.score \
  --engine /tmp/engine.json --format sqlflow-mvp --ignore-schema
```

## EAI 계층 — 시스템 경계를 넘는 구간

`syneai/` 는 webMethods Integration Server 패키지를 합성한다. PL/SQL 계층과 성격이
정반대다 — 매핑은 `MAPCOPY` 로 **명시적**이라 SQL 해석이 필요 없지만, 난점이 세 군데
따로 있다.

### 1. 리니지가 바이너리 블롭 안에만 있다

`flow.xml` 어디에도 테이블명·컬럼명이 없다. 어느 DB의 어느 스키마, 어느 테이블,
어느 컬럼에 쓰는지는 `node.ndf` 의 base64 `IRTNODE_PROPERTY` 안에만 있다.

```sh
python3 -m syneai.wmvalues --dump samples-eai/SYN_WMS_S_0001/adpt/IF_ITEM_RCV_I_01/node.ndf
```

특히 `update.expression` 의 `SYNCRYPT.FN_ENC(?)` 같은 DB측 함수는 소스 어디에도 SQL
텍스트로 나타나지 않는다. **개인정보 컬럼이 어디서 암호화되는지는 소스 검색으로 찾을 수
없고, 블롭을 해석해야만 나온다.** 실무 가치가 가장 큰 지점이다.

> **바이너리 포맷은 실제 webMethods 와의 호환성이 검증되지 않았다.** 관측 가능한 표본이
> 33바이트 1건뿐이었기 때문이다. 무엇이 관측이고 무엇이 규약인지, 실제 표본이 생겼을 때
> 어떻게 대조하는지는 [docs/WM-VALUES-FORMAT.md](docs/WM-VALUES-FORMAT.md)에 분리해
> 기록했다. 태그 표는 `wmvalues.py` 한 곳에만 있어 교체가 쉽다.

### 2. 컬럼명이 경계에서 바뀐다

`SYNSRC.SRC_ITEM_MST.ITM_CODE` → `SYNIF.IF_ITEM_RCV.ITEM_CD`. 이름으로 컬럼을 잇는
엔진은 EAI 구간에서 전부 틀린다. 그래서 `SYNSRC` 의 컬럼명은 대응하는 `SYNIF` 컬럼과
의도적으로 다르게 지었다.

### 3. 파이프라인은 전역 상태다

`MAPCOPY` 를 전부 모아 리니지라고 부르면 답이 그럴듯하게 틀린다. `MAPDELETE` 나
`pub.flow:clearPipeline` 이 중간에 끼면 그 뒤의 적재는 값이 없다.

```
MAPCOPY  .../ITM_NAME_LO  →  /IF_ITEM_RCV/ITEM_NM     ← 매핑은 분명히 존재한다
MAPDELETE                    /IF_ITEM_RCV/ITEM_NM     ← 그러나 여기서 지워지고
INVOKE   IF_ITEM_RCV_I_01                             ← 적재는 그 다음이다
```

정답은 `SEVERED` 다. `pipeline.py` 는 스텝을 **실행 순서대로 재생**해 파이프라인 상태를
읽어내며, 정답은 스텝 목록이 아니라 그 상태에서 나온다. 생성된 코퍼스의 SEVERED 77건이
이 감별 항목이다.

### 티어

| Tier | 내용 | 비중 |
|---|---|---:|
| **0** | Select → MAPCOPY 1:1 → Insert | 20% |
| **1** | 스테이징 경유, 3·4단 중첩 경로, MAPSET 상수, MAPINVOKE 변환기 | 35% |
| **2** | LOOP 배열, **MAPDELETE 단절**, Update 어댑터 WHERE | 30% |
| **3** | BRANCH 조건부 적재, **clearPipeline**, CustomSQL | 15% |

Tier 2의 `MAPDELETE` 와 Tier 3의 `clearPipeline` 을 무시하는 엔진은 Tier 0~1에서
만점을 받고 Tier 2에서 무너진다.

### 구문 분포

실측 표본(인터페이스 2건 / FLOW 서비스 6개)을 두 축으로 나눠 재현한다. 필드 수에
비례하는 구문은 MAPCOPY 대비 비율로, 스텝 블록 단위로 존재하는 구문은 서비스당 개수로
관리한다. 한 축으로 묶으면 좁은 스키마에서 구조적 구문이 부당하게 줄어든다.

```
metric              기준    target    actual   target 수  actual 수  판정
MAP           /MAPCOPY     0.804     0.778       1003       971  OK
MAPDELETE     /MAPCOPY     0.482     0.361        602       451  OK
MAPINVOKE     /MAPCOPY     0.080     0.078        100        97  OK
INVOKE        /service    10.000    10.000       1200      1200  OK
BRANCH        /service     0.670     0.658         80        79  OK
depth 3       /MAPCOPY     0.573     0.562        715       701  OK
```

`MAPCOPY` 경로 깊이 분포(1단 23.6% / 2단 16.1% / 3단 57.3% / 4단 3.0%)는 생성 시점에
정확히 배분한다. 그냥 두면 3단이 거의 전부가 된다.

### EAI 자체 검증

`python3 -m syneai.validate` 는 24종을 확인한다. PL/SQL 쪽과 같은 자세이되, 여기서는
더 중요하다 — 리니지를 담은 메타데이터가 바이너리라 인코더와 정답이 어긋나도 아무도
눈치채지 못하기 때문이다.

- 모든 블롭이 디코딩되고 재인코딩이 **바이트 단위로 일치**하는가
- 블롭의 `tables.columnInfo` 가 DDL 카탈로그와 **정확히 일치**하는가
- 정답 엣지의 타깃 컬럼이 그 블롭의 `update.column` 에 실제로 있는가 (455건 대조)
- `SEVERED` 로 표기된 필드에 대응하는 `MAPDELETE` 가 flow.xml 에 실재하는가
- 모든 flow.xml / node.ndf 가 정상 XML 인가
- **표본에서 관측된 식별자가 생성물에 하나도 없는가** (반출 제약)
- 동일 seed → 동일 코퍼스

### 수작업 픽스처

`fixtures-eai/` 9건. flow.xml 과 라벨은 손으로 썼고, 블롭만 인코더가 만든다(그것 말고는
만들 방법이 없다). 즉 라벨은 파이프라인 시뮬레이터와 독립적이며, 그 시뮬레이터가 가장
틀리기 쉬운 부분이다.

| 픽스처 | 검증 대상 |
|---|---|
| `E01_blob_holds_the_binding` | 블롭 없이는 엣지가 하나도 나오면 안 됨 |
| `E02_column_names_differ` | 컬럼명이 경계에서 바뀜 |
| `E03_mapdelete_severs_lineage` | 매핑은 있으나 정답은 SEVERED |
| `E04_expression_only_in_blob` | DB측 암호화 함수는 블롭 안에만 |
| `E05_mapinvoke_transformer` | 인라인 변환기 = TRANSFORM |
| `E06_mapset_constant` | 원천 없는 대입 = CONSTANT |
| `E07_clearpipeline_mass_sever` | 스텝 하나가 앞선 매핑 전부를 무효화 |
| `E08_select_filter_is_indirect` | Select WHERE = INDIRECT_FILTER |
| `E09_customsql_needs_sql_parser` | UNRESOLVED가 정답. SQL 파서 재사용 지점 |

## 통합 정답셋

`--merge` 는 두 계층의 정답을 합쳐 `out/lineage_truth_merged.json` 을 만들고, 원천
시스템에서 리포트까지 이어지는 체인을 보고한다.

```
전 구간 체인 15홉:
  SYNARC.ARC_OUT_SHIP.SHIP_SEQ
   <- SYNWMS.OUT_SHIP.SHIP_QTY  <- … <- SYNWMS.MST_ITEM.ITEM_CD
   <- SYNIF.IF_ITEM_RCV.ITEM_CD          ← 여기가 EAI 접합점
   <- SYNSRC.SRC_ITEM_MST.ITM_CODE       ← 원천 시스템
```

`SYNIF` 를 사이에 두고 EAI 엣지와 PL/SQL 엣지가 이어진다. 두 생성기가 같은
`schema.py` 와 같은 엣지 분류를 쓰기 때문에 별도 변환 없이 하나의 그래프가 된다.

## 모듈 구성

| 파일 | 역할 |
|---|---|
| `profile.json` | 구문 분포 사양. 생성기의 입력 |
| `synplsql/schema.py` | 가상 스키마 26개 테이블 / 3개 스키마, 리니지 플로우, DDL 생성 |
| `synplsql/core.py` | IR 모델 + 렌더러 + 리니지 추출기 |
| `synplsql/scenarios.py` | 구문 패밀리별 시나리오 빌더, 구문 쿼터 |
| `synplsql/generate.py` | CLI 드라이버, 정답 직렬화, 프로파일 대조 |
| `synplsql/validate.py` | 코퍼스·정답셋 자체 검증, 픽스처 검사 |
| `synplsql/score.py` | 엔진 출력 채점 |
| `profile-eai.json` | FLOW 구문 분포 사양 |
| `syneai/wmvalues.py` | webMethods `Values` 바이너리 인/디코더 |
| `syneai/adapters.py` | JDBC 어댑터 4종 + `IRTNODE_PROPERTY` 블롭 생성 |
| `syneai/docs.py`, `nodes.py` | IS 문서 타입, 인터페이스·서비스 노드 |
| `syneai/flow.py` | FLOW IR + XML 렌더러 + 파이프라인 경로 문법 |
| `syneai/interfaces.py` | 인터페이스 조립, 경로 깊이·구문 비율 제어 |
| `syneai/pipeline.py` | 파이프라인 상태 시뮬레이터 (정답 산출) |
| `syneai/generate.py` | EAI CLI + 두 계층 정답셋 병합 |
| `syneai/validate.py` | EAI 자체 검증 + 픽스처 검사 |

## 한계

- 생성 코드는 실행 가능한 SQL이 아니다. 시퀀스가 서브쿼리 안에 놓이는 등 실행 시점
  제약은 지키지 않는다. 목적이 파싱과 리니지 해석이므로 **구조적 충실도 > 의미적 충실도**
  원칙을 따른다.
- 합성 코드는 실제 코드보다 규칙적이다. 템플릿 다양화·랜덤 별칭·힌트 삽입으로 완화했지만,
  최종 검증은 실제 코퍼스로 (로컬 한정) 해야 한다.
- `PIVOT`, `FORALL` 등 실측 출현이 극히 드문 구문은 표본이 작아 통계적 대조의 의미가 약하다.
- **EAI 블롭의 실제 webMethods 호환성은 검증되지 않았다.** 관측 표본이 33바이트 1건뿐이라
  배열·레코드 태그를 관측할 수 없었다. 이 코퍼스를 통과한 디코더가 실제 운영 블롭도
  읽는다는 보장은 없으며, 그 보장은 실제 표본으로만 얻을 수 있다.
  ([docs/WM-VALUES-FORMAT.md](docs/WM-VALUES-FORMAT.md))
- EAI 실측 표본이 인터페이스 2건뿐이라 FLOW 구문 분포의 통계적 신뢰도는 낮다. 비율은
  설계 목표치로 다루는 편이 맞다.
