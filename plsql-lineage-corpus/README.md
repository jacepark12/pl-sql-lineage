# 합성 PL/SQL 코퍼스 생성기

컬럼 레벨 리니지 엔진의 개발·검증에 쓰는 **합성 PL/SQL 코퍼스**와 **리니지 정답셋**을
생성한다. 설계 배경과 근거는 [docs/PLAN.md](docs/PLAN.md)에 있다.

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

# 기본 코퍼스 생성 (200 패키지 / 약 35만 라인, 4초 내외)
python3 -m synplsql.generate --out out --stats

# 개발 초기에는 쉬운 티어만 빠르게
python3 -m synplsql.generate --tier 0,1 --packages 20 --lines 30000 --out out/dev

# 생성 결과 자체 검증 (정답셋 무결성 + 재현성)
python3 -m synplsql.validate --out out

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

`out/` 은 `.gitignore` 대상이다. 커밋된 `samples/` 에 6개 패키지 분량의 생성 예시가
들어 있으므로, 실행 없이도 산출물의 형태를 확인할 수 있다.

## 기본 코퍼스 (seed 20260812)

| 지표 | 값 |
|---|---:|
| 패키지 | 201 |
| 총 라인 | 346,573 |
| 프로시저 / 함수 | 822 / 86 |
| 최대 패키지 | 37,585 라인 |
| 리니지 엣지 | 10,832 |
| REF CURSOR 투영 | 181 |
| 최장 리니지 체인 | 15홉 |

엣지 종류 분포:

| 종류 | 건수 | 의미 |
|---|---:|---|
| `DIRECT` | 3,419 | 단순 컬럼 대입 |
| `TRANSFORM` | 1,980 | 함수·연산 경유 |
| `AGGREGATE` | 178 | 집계함수. 여러 행이 한 값으로 접힘 |
| `ANALYTIC` | 251 | 분석함수 (PARTITION/ORDER 컬럼 포함) |
| `VIA_CTE` | 541 | CTE·인라인 뷰 경유 (전이 해석 필요) |
| `VIA_VARIABLE` | 754 | PL/SQL 변수·커서 레코드·컬렉션 경유 |
| `INDIRECT_FILTER` | 3,583 | WHERE / JOIN / GROUP BY / CASE 조건절 |
| `UNRESOLVED` | 126 | 동적 SQL. 정적 해석 불가 |

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
구문 프로파일 대조  (파일 201개 / 346,573 라인)
construct           target/1K  actual/1K    target   actual   판정
CASE_WHEN               12.66      10.89      4388     3775   OK
TYPE_ANCHOR             13.24      14.68      4589     5087   OK
UPDATE_SET               1.87       2.06       648      713   OK
INSERT_INTO              1.52       2.03       527      704   OK
REF_CURSOR               1.21       0.96       419      332   OK
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
| 엣지 Precision | 76.9% |
| 엣지 Recall | 69.8% |
| 엣지 F1 | 73.1% |
| Kind 정확도 (개략) | 60.9% |
| 다홉 완주율 | 42.6% |

문장 단위 정확도(F1 73.1%)에 비해 다홉 완주율이 절반 이하로 떨어지는 것이 눈에 띈다.
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

## 한계

- 생성 코드는 실행 가능한 SQL이 아니다. 시퀀스가 서브쿼리 안에 놓이는 등 실행 시점
  제약은 지키지 않는다. 목적이 파싱과 리니지 해석이므로 **구조적 충실도 > 의미적 충실도**
  원칙을 따른다.
- 합성 코드는 실제 코드보다 규칙적이다. 템플릿 다양화·랜덤 별칭·힌트 삽입으로 완화했지만,
  최종 검증은 실제 코퍼스로 (로컬 한정) 해야 한다.
- `PIVOT`, `FORALL` 등 실측 출현이 극히 드문 구문은 표본이 작아 통계적 대조의 의미가 약하다.
