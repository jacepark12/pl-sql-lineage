# 엔진 구현 현황과 남은 작업

설계와 그 근거가 된 측정은 [engine-architecture.md](engine-architecture.md)에 있습니다.
이 문서는 **어디까지 했고 다음에 무엇을 하는가**만 다룹니다.

## 현재 상태

| 계층 | 상태 | 파일 |
|---|---|---|
| A — PL/SQL 구조 | 완료 | `parser.py`, `structure.py` |
| B — 문장 내부 (sqlglot) | Tier 0~2 합성 코퍼스 100%. DB link 는 `schema.table@LINK` 로 로컬과 구분 | `sqlmap.py` |
| C — 문장 간 변수 데이터플로 | 구현·검증 완료 | `dataflow.py` |

Tier 0~1 채점 결과입니다. 규모를 두 배로 늘려도 같습니다 — 처음 맞춘 9 파일에
과적합된 것이 아닙니다.

| | 9 패키지 / 12,059 라인 | 21 패키지 / 고유쌍 312 |
|---|---|---|
| 파싱 성공률 | 100.0% (10/10) | 100.0% (21/21) |
| 엣지 F1 | 100.0% (P 100 / R 100) | 100.0% (P 100 / R 100) |
| Kind 정확도 | 100.0% (정밀·개략) | 100.0% (정밀·개략) |
| 다홉 완주율 | 100.0% (46/46) | 100.0% (103/103) |

Tier 2 합성 코퍼스 (MERGE / CTE / `SELECT *` / 집계 / 분석함수, 16 패키지 / 24,992 라인 / 고유쌍 397):

| | Tier 2 |
|---|---|
| 파싱 성공률 | 100.0% (16/16) |
| 엣지 F1 | 100.0% (P 100 / R 100) |
| Kind 정확도 | 100.0% (정밀·개략) |
| 다홉 완주율 | 100.0% (221/221) |

**이 100% 는 "엔진 완성" 이 아닙니다.** Tier 0~1 의 천장이 원래 100% 이고
(변수 경유도 동적 SQL 도 없는 구간) 거기 도달했다는 뜻입니다. Tier 2 의 문장 단위
천장 추정은 96.7% 였는데, MERGE·CTE·`SELECT *` 를 넣은 뒤에는 이 샘플에서 100% 가
나왔습니다. 라인 비중으로 0~1 은 54.8% 로 쉬운 쪽 절반이고, 전 티어 기준으로는
A·B 만으로 다홉 완주율 48.3% 가 천장입니다.

재현:

```sh
cd plsql-lineage-corpus && python3 -m synplsql.generate --tier 0,1 --packages 20 --lines 30000 --out out/dev
cd ../plsql-lineage-engine && python3 scripts/build_parser.py
python3 -m plsqllineage.engine --input ../plsql-lineage-corpus/out/dev --out /tmp/engine.json
cd ../plsql-lineage-corpus && python3 -m synplsql.score \
  --truth out/dev/lineage_truth.json --manifest out/dev/manifest.json \
  --engine /tmp/engine.json --format generic
```

`--input` 은 코퍼스 **루트**를 가리켜야 합니다. `packages/` 하위를 가리키면
`location.file` 이 정답셋 규약(`packages/X.sql`)과 어긋나 티어별 표가 전부 0% 로 나옵니다.

## C 계층 측정 결과

같은 Tier 3 코퍼스(15 패키지 / 26,070 라인)에 **C 없이 한 번, C 넣고 한 번** 돌렸습니다.
B 의 미지원 구문은 양쪽에 똑같이 깔리므로 차이가 곧 C 의 기여입니다.

| | A+B | A+B+C | 차이 |
|---|---:|---:|---:|
| 엣지 F1 | 76.9% | 78.6% | +1.7 |
| Precision | 87.5% | 90.1% | +2.6 |
| Recall | 68.6% | 69.7% | +1.1 |
| 다홉 완주율 | 33.5% | 36.1% | +2.6 |
| `VIA_VARIABLE` 엣지 | 0 | 15 | +15 |

**C 는 동작하지만 기여가 작습니다. B 의 구멍에 막혀 있기 때문입니다.**
놓친 116 쌍을 분해하면 원인이 C 가 아닙니다.

| 놓친 것 | 건수 | 책임 |
|---|---:|---|
| `via=DERIVED` (MERGE 의 USING) | 30 | B — MERGE 미지원 13건 |
| `VIA_CTE` | 15 | B — CTE 미관통 |
| `INDIRECT_FILTER` / `DIRECT` | 대부분 | B — 미분석 MERGE 에서 파생 |
| `VIA_VARIABLE` | 6 | C |

이 시점의 결론은 "병목이 MERGE 와 CTE" 였지만, **틀렸습니다.** 뒤의 실무 측정에서
드러난 `_alias_map` / `INSERT ... VALUES` 두 결함이 더 앞에 있었습니다. 두 건을 고치자
같은 Tier 3 코퍼스에서 다홉이 아래처럼 움직였습니다.

| Tier 3 | A+B | A+B+C | +결함 2건 수정 |
|---|---:|---:|---:|
| 엣지 F1 | 76.9% | 78.6% | **79.9%** |
| Recall | 68.6% | 69.7% | **71.6%** |
| 다홉 완주율 | 33.5% | 36.1% | **43.7%** |

**결함 2건 수정이 C 계층 자체(+2.6)보다 다홉을 크게 올렸습니다(+7.6).** C 가 굶고 있었던
것이지 C 가 약했던 것이 아닙니다. MERGE·CTE 는 여전히 남은 병목이지만 첫 번째는 아니었습니다.

Tier 0~1 회귀 없음 — C 적용 후에도, 결함 2건 수정 후에도 전 지표 100% 유지
(다홉 103/103).

C 가 처리하는 두 가지 형태입니다.

```sql
-- 1. BULK COLLECT: 컬렉션 필드로 바인딩
SELECT r.UNIT_WGT AS UNIT_WGT BULK COLLECT INTO t_rows FROM SYNIF.IF_ITEM_RCV r;
FORALL i IN 1 .. t_rows.COUNT
  UPDATE SYNWMS.MST_ITEM t SET t.UNIT_WGT = t_rows(i).UNIT_WGT;
--   -> VIA_VARIABLE hops=2  MST_ITEM.UNIT_WGT <- IF_ITEM_RCV.UNIT_WGT

-- 2. 커서 루프 누적: 커서 SELECT -> 레코드 필드 -> 변수 -> 뒤의 DML
CURSOR c_pick IS SELECT j.ALLOC_QTY AS PICK_QTY FROM SYNWMS.OUT_ALLOC j;
FOR rec IN c_pick LOOP  v_acc_qty := NVL(v_acc_qty,0) + NVL(rec.PICK_QTY,0);  END LOOP;
```

## 실무 코드 측정 (2026-08-25)

합성 코퍼스 밖의 운영 PL/SQL 을 처음 넣었습니다. 소스는 커밋하지 않으며(아래
[validation-limits.md](validation-limits.md) 의 규약), 여기에는 측정치만 남깁니다.

| 묶음 | 규모 | 파싱 | 엣지 | 진단 |
|---|---|---|---|---|
| WMS/EAI 트리거·프로시저·패키지 12파일 | 18,413 라인 | 5/12 | 73 | `PARSE_FAILED` 7, `SQL_NOT_ANALYZED` 3 |
| `PG_OT_ORDERS` 패키지 바디 1파일 | 842 라인 | 1/1 | 26 | 0 |

처리량은 40 라인/s 와 16 라인/s 로, README 의 웜 실측치(957 라인/s)와 자릿수가 다릅니다.
30 만 라인 추정치(워밍업 75 초 + 약 5 분)는 실무 표기에서 성립하지 않습니다.

### A 계층 — 통과. 단 진입 지점 하나

`EDITIONABLE`, 인용 식별자 `"WMSADM"."PG_OT_ORDERS"`, UTF-8 BOM 은 모두 문제없이
처리됩니다. 파싱 실패 7 건은 전부 한 가지 원인이었습니다.

```
mismatched input 'FN_TPL_POSSIBLE_DATE' expecting {<EOF>, '/', ';'}
```

실패 파일이 `CREATE OR REPLACE` 없이 객체 키워드부터 시작합니다 — `ALL_SOURCE.TEXT` 를
그대로 뽑으면 나오는 모양이라 실무 자산에서는 이쪽이 오히려 기본형입니다. 합성 코퍼스는
생성기가 항상 `CREATE OR REPLACE` 를 찍으므로 **0 건**입니다. 앞에 접두사를 붙여 재시험한
결과 7 건 중 6 건이 오류 0 으로 통과했고, 나머지 1 건은 소스에 편집 마커(`!! 여기`)가 박힌
진짜 불량 소스라 거부가 옳습니다.

읽기 인코딩은 `utf-8` 다음 `cp949` 입니다. 둘 다 실패하면 해당 파일만 `DECODE_FAILED` 이고
런 전체가 죽지 않습니다. `CREATE OR REPLACE` 없이 `PROCEDURE`/`FUNCTION`/`TRIGGER`/`PACKAGE`
로 시작하는 `ALL_SOURCE.TEXT` 형태는 접두사를 붙여 파싱합니다. 편집 마커 같은 불량 소스는
접두하지 않고 `PARSE_FAILED` 를 유지합니다.

### B 계층 — 새 결함 2 건 (수정 완료, 커밋 `360aa34`)

`PG_OT_ORDERS` 한 파일을 문장 단위로 계측한 결과입니다.

```
문장 104 (DML 18 / 대입 86)
엣지 원본 30 → 유지 26
탈락: 미분석 0 / 엣지0 14 / 미해결버림 4 / 대입미결 84
```

**`INSERT ... VALUES` 가 엣지를 하나도 내지 않습니다 (수정됨).** `sqlmap.py:349` 가
`return []` 하면서 주석에 "INSERT ... VALUES handled by the caller" 라고 적어 두었지만
호출자는 처리하지 않습니다 — `analyze()` 는 `exp.Insert` 를 `_HANDLERS` 로 `_insert` 에
넘기고 끝이며 VALUES 분기가 없습니다.

| 입력 | 엣지 |
|---|---|
| `INSERT INTO T (A) VALUES (V_X)` | 0 |
| `INSERT INTO T (A) VALUES (SRC.B)` | 0 |
| `INSERT INTO T (A) SELECT s.B FROM SYN.S s` | 1 |

이 파일에는 `IFADM.ORDERS_IOILINK` 로 17 컬럼을 적재하는 INSERT 가 2 건 있습니다. 여기서만
34 개 엣지가 사라지며, 이는 엔진이 파일 전체에서 낸 26 개보다 많습니다. 인터페이스 테이블
적재는 `원천 → EAI → 인터페이스 테이블 → PL/SQL` 체인의 접합부이므로 영향이 큽니다.

**`_alias_map` 이 `INTO` 대상을 테이블로 취급합니다 (수정됨).** sqlglot 은 `INTO V_QTY` 를
`exp.Table` 로 표현하는데 `_alias_map`(`sqlmap.py:87`)이 이를 FROM 테이블과 같이 담습니다.
한정자 없는 컬럼이 후보 테이블 2 개 사이에서 모호해져 해소에 실패합니다.

```
SELECT QTY INTO V_QTY FROM TASKDETAIL
  tables: ['V_QTY', 'TASKDETAIL']     <- V_QTY 는 변수지 테이블이 아니다
  _sources: ([], ['QTY'], [])         <- 미해결
```

이 파일의 `SELECT ... INTO` 12 건 중 8 건이 바인딩 0 개였습니다. `find_all(exp.Table)`
루프에서 `table.find_ancestor(exp.Into) is not None` 이면 건너뛰도록 해서 풀었습니다.

| | 현재 | 수정 후 |
|---|---|---|
| `SELECT QTY INTO V_QTY FROM TASKDETAIL` | 0 | `V_QTY <- TASKDETAIL.QTY` |
| `SELECT SUM(QTY) INTO V_TASK_QTY ...` | 0 | `V_TASK_QTY <- TASKDETAIL.QTY` |
| `SELECT NVL(MAX(FAC_CD),' ') INTO ...` | 0 | `V_CJON_CHK <- FWADM.CENT_LIST.FAC_CD` |
| `SELECT COUNT(*) INTO V_TEMP ...` | 0 | 0 (소스 컬럼 없음, 정상) |
| 다중 타깃 `INTO V_TEMP, V_QTY` | 2 | 2 (회귀 없음) |

`MERGE` 미지원은 12 파일 묶음에서 3 건으로 재확인되었습니다. 이미 알려진 구멍입니다.

### C 계층 — 위의 연쇄로 굶습니다

대입문 86 건 중 리터럴 66 건은 소스가 없으니 바인딩 실패가 정상입니다. 문제는 나머지
20 건 중 18 건이 실패한다는 것입니다(변수 단순복사 10/10, 문자열결합 8/10). 변수가 채워진
적이 없으니 복사할 것도 없습니다 — B 계층 결함의 하류입니다. 그 결과
`UPDATE ORDERS SET STAT_CD = V_NEW_STAT` 류의 엣지 4 개가 `engine.py:119` 의
`if not edge.sources: continue` 에서 버려집니다.

로드맵은 C 를 "구현·검증 완료 (B 의 구멍에 막혀 있음)" 로 적어 두었는데, 실무 코드에서
막는 구멍은 `MERGE`·CTE 가 아니라 위의 두 건이었습니다. 두 건을 고친 뒤
`SELECT INTO -> 변수 -> INSERT ... VALUES` 체인이 복원됩니다.

```
[VIA_VARIABLE hops=2] IFADM.ORDERS_IOILINK.IF_QTY  <- SYNWMS.OUT_ORDER_D.ORD_QTY
```

### 탈락이 전부 조용합니다

세 지점이 진단을 남기지 않습니다.

| 지점 | 위치 |
|---|---|
| `assignment_binding` 이 `None` | `engine.py:107` |
| `resolve_edges` 결과에 `sources` 가 빔 | `engine.py:119` |
| 분석 성공했으나 `result.edges` 가 빔 | 진단 자체가 없음 |

`PG_OT_ORDERS` 는 40 개 가까운 엣지를 잃으면서 **진단 0 건**으로 끝났습니다. 엣지 밀도도
30.9 엣지/1K 라인으로 합성 코퍼스(28.7)와 같은 수준이라 신호가 되지 못합니다. 조용한 탈락에
진단을 심기 전에는 실무 코드에서 무엇을 잃는지 측정할 수단이 없습니다.

이후 `resolve_edges` 빈 소스 탈락은 `PARAMETER_UNRESOLVED` / `UNRESOLVED` 를 냅니다.
`O_ERRCODE := 404` 같은 리터럴 대입(`assignment_binding is None`)은 그대로 무음입니다.

## 검증되지 않은 것

- **Tier 2** — `MERGE`, CTE, 집계/분석함수, `SELECT *`, `(+)` 조인은 합성 코퍼스
  16패키지 샘플에서 전 지표 100% 입니다. DB 링크는 `schema.table@LINK` 로 로컬 테이블과
  구분되며 엣지 `table` / `dblink` 에 보존됩니다.
- **전체 코퍼스 30만 라인** — 실측 있음. 기본 코퍼스(201 패키지 / 300,612 라인)를
  한 프로세스에서 돌리면 파싱 201/201, 벽시계 183.5s, **1,638 라인/s**
  (웜 1,737 라인/s). 숫자는 [scoring-runs.md](scoring-runs.md) JAC-160.
  README 의 파서 전용 웜 추정치 957 라인/s 보다 이 환경에서는 빠르고, 실무 표기
  13 라인/s 와는 자릿수가 다릅니다.
- **실무 PL/SQL** — 1 차 측정을 했습니다(위 절). 다만 19,255 라인 / 13 파일이고 전부 같은
  WMS·EAI 계열이라 표기 다양성의 일부만 봤습니다. 정답셋이 없어 P/R/F1 은 여전히
  측정 불가입니다. 무엇을 잴 수 있고 없는지는
  [validation-limits.md](validation-limits.md)에 정리했습니다

## 남은 작업

### 1. Tier 2 로 범위 확대 — 우선순위 1

아래 구멍은 짧은 SQL 을 엔진에 직접 넣어 확인한 것이며, 추정이 아닙니다.

Tier 2 를 먼저 하는 이유는 두 가지입니다. B 의 실제 한계가 드러나고, 동시에 변수 경유와
다문장 전이가 처음 등장해 **C 를 검증할 재료가 생깁니다.** C 를 먼저 만들면 Tier 0~1 에는
변수 경유가 없어 점수가 움직이지 않고, 검증 없이 코드만 쌓입니다.

알려진 구멍:

- ~~`INSERT ... VALUES` 가 엣지를 내지 않습니다~~ — 수정됨 (`360aa34`). Tier 2 시나리오
  `SELECT INTO -> INSERT ... VALUES`(`scenarios.py:893`)가 이 형태이므로 Tier 2 채점에
  바로 반영됩니다.
- ~~`_alias_map` 이 `INTO` 대상을 테이블로 셉니다~~ — 수정됨 (`360aa34`).
- ~~`MERGE` 미지원.~~ — 지원됨. `WHEN MATCHED THEN UPDATE` 와
  `WHEN NOT MATCHED THEN INSERT` 를 읽고, `ON` / USING 필터는 `INDIRECT_FILTER` 로
  남깁니다. USING 서브쿼리는 투명한 파생 테이블이라 소스는 원천 테이블입니다.
- ~~CTE 가 깨져 있습니다.~~ — 관통됨. `WITH c AS (SELECT s.X ...) SELECT c.X` 는
  `T.A <- SYN.S.X` (`VIA_CTE`) 를 냅니다. 인라인 뷰도 같은 홉입니다. recursive CTE 는
  전개하지 않고 `UNSUPPORTED_CTE` 진단을 남깁니다.
- ~~`SELECT *` 는 엣지를 하나도 내지 않습니다.~~ — `ddl/catalog.sql` 을 읽어
  `*` / `alias.*` 를 컬럼 목록으로 전개합니다. 카탈로그가 없으면 `STAR_UNRESOLVED`
  진단만 남기고 지어내지 않습니다.
- **`(+)` 구식 외부 조인은 문제없습니다 (확인됨).** sqlglot 이 Oracle 방언에서 파싱합니다.
- ~~**DB 링크 `@LINK`**~~ — `table@LINK` / `schema.table@LINK` 를 로컬 테이블과 다른
  식별자로 보존합니다. 엣지 JSON 은 `table` 에 Oracle 표기(`SYN.T@REMOTE`)를 쓰고
  `dblink` 필드를 같이 냅니다. 식별할 수 없는 `@` 형태는 `DB_LINK_UNRESOLVED` 진단입니다.

목표: Tier 2 천장은 문장 단위 완벽 엔진 기준 F1 96.7% 입니다. 그 아래는 전부 결함입니다.

### 2. C 계층 — 구현 완료, 남은 정밀도 과제

`dataflow.py` 로 구현되어 있고 위 「C 계층 측정 결과」 절에 수치가 있습니다. 남은 것은
정확도이지 기능이 아닙니다.

- **제어 흐름 평탄화의 정밀도.** A 계층이 `IF`/`LOOP` 중첩을 펴서 문장을 소스 순서로 냅니다.
  `IF` 안의 대입도 "그 변수가 그 값을 **가질 수 있다**" 로 읽는 근사이며, 리니지 용도로는
  타당하지만 손실 가능성은 아직 측정하지 않았습니다.
- **`%ROWTYPE` 은 앵커를 만들지 않습니다.** 테이블은 알지만 컬럼이 특정되지 않기 때문입니다.
  커서 레코드(`FOR rec IN c LOOP`)는 커서 SELECT 의 투영으로 따로 처리하지만,
  `r  T%ROWTYPE` 로 선언된 레코드의 필드 접근은 아직 따라가지 못합니다.
- **`%TYPE` 앵커를 아직 쓰지 않습니다.** `structure` 가 수집해 두었지만(Tier 0~1 에서 161개)
  C 는 `SELECT INTO` 로 실제 채워진 값만 사용합니다. 앵커를 바인딩으로 쓰면 커버리지는
  오르지만 "선언 타입" 을 "실제 흐른 값" 으로 오인할 위험이 있어 보류 중입니다.

### 3. Tier 3

`BULK COLLECT` 와 REF CURSOR 는 C 계층과 맞물립니다. 정답셋은 REF CURSOR 투영을
`ref_cursors` 로 따로 기록하므로 채점 대상이 다릅니다.

동적 SQL 은 **잡지 않는 것이 정상**입니다. 정답셋이 `UNRESOLVED` 로 명시해 P/R 계산에서
제외하므로, 엔진은 이를 진단으로 내되 리니지를 지어내지 않아야 합니다. `EXECUTE IMMEDIATE`
와 `OPEN ... FOR <표현식>` 은 `DYNAMIC_SQL` 진단(파일·라인·패키지·프로시저)을 남기고
SQL 문자열에서 엣지를 만들지 않습니다. 문자열 리터럴 / 변수 조립 / `USING` 바인드 여부는
메시지에 기록합니다. 런타임 로그로 동적 SQL 을 해소하는 것은 이 엔진의 범위가 아닙니다.

### 4. 전체 코퍼스 실행 — 실측 완료 (JAC-160)

기본 합성 코퍼스(seed `20260812`, `--out out/full`)를 엔진 + scorer 로 한 번 돌렸습니다.
명령·채점표·병목은 [scoring-runs.md](scoring-runs.md) 에 있습니다.

| | 값 |
|---|---|
| 규모 | 201 패키지 / 300,612 라인 / 정답 엣지 8,629 |
| 파싱 | 201/201, `PARSE_FAILED` 0 |
| 벽시계 | 183.5s (user 173.7s / sys 9.6s), peak RSS 459 MiB |
| 처리량 | 전체 1,638 라인/s · 첫 파일 44.4 · 이후 웜 **1,737 라인/s** |
| parse vs 나머지 | parse 153.1s (83.5%) / sqlmap+dataflow 30.3s |
| 고유쌍 F1 | 96.7% (P 95.1 / R 98.4). Tier 0~2 는 100%, Tier 3 은 91.9% |
| 다홉 | 90.1% (1,758/1,950) |

한 프로세스 DFA 캐시는 실제로 이득입니다 — 첫 파일 44 라인/s vs 웜 1,737.
프로세스마다 워밍업을 다시 물면 이 숫자가 무너집니다. 병목은 sqlmap 이 아니라
ANTLR 파싱(및 워밍업 구간의 작은 파일)입니다. 가장 큰 패키지(32,655 라인)는
웜 상태에서 2,197 라인/s 로, 규모 자체가 느린 것은 아닙니다.

남은 정확도 구멍은 전 코퍼스 규모가 아니라 **Tier 3** 입니다(고유쌍 FN 16 / FP 50,
시퀀스 `NEXTVAL`·패키지 전역·레코드 필드 `UNRESOLVED` 진단). EAI 계층은 이 엔진이
읽지 않으므로 돌리지 않았습니다. 실무 13 라인/s 는 비공개 SQL 없이 재현하지 않습니다.

### 5. 산출물 연결

- **뷰어** — `web/index.html` 이 읽는 `objects` / `relationships` 계약으로 내보내는
  출력 형식 추가. 현재 엔진은 정답셋 형식(`edges`)만 냅니다.
- **저장 계층** — [column-lineage-schema.md](column-lineage-schema.md) 의 3개 테이블.
  엔진 출력이 안정된 뒤의 작업입니다.

## 우선순위 요약

```
[완료] _alias_map 의 INTO 제외        360aa34 - 다홉 36.1% -> 43.7%
[완료] INSERT ... VALUES 핸들러       360aa34 - 위와 한 묶음
[완료] C 계층 (변수 데이터플로)         dataflow.py
[완료] MERGE 지원                     MATCHED / NOT MATCHED / ON
[완료] CTE 관통                       VIA_CTE, 원천 테이블까지. recursive 는 진단
[완료] SELECT * 전개                  ddl/catalog.sql. 없으면 STAR_UNRESOLVED
[완료] 동적 SQL 진단                  EXECUTE IMMEDIATE / OPEN FOR → DYNAMIC_SQL. 엣지 없음
[완료] 빈 소스 탈락 진단              매개변수는 PARAMETER_UNRESOLVED (호출자 필요). 리터럴은 무음
[완료] CREATE 없는 ALL_SOURCE 소스    CREATE OR REPLACE 접두. 불량 소스는 PARSE_FAILED
[완료] 인코딩 utf-8 → cp949           UnicodeDecodeError 로 전체 런을 죽이지 않음
[완료] DB link 객체 식별              SYN.T@REMOTE ≠ SYN.T. 엣지에 dblink 보존
[완료] 전체 코퍼스 실행 (JAC-160)     201 pkg / 300,612 lines, 183.5s, 1,638 라인/s, F1 96.7%

1. 조용한 탈락 커버리지 리포트        매개변수 탈락은 진단됨. 전 문장 커버리지 리포트 형식은 미정
2. Tier 3 정밀도 / 뷰어 출력 형식 / 저장 계층
```

완료 항목 셋은 모두 Tier 0~1 회귀(F1 100%, 다홉 103/103)를 확인한 뒤 반영했습니다.
남은 항목도 같은 절차를 따릅니다.

1 번은 **사람이 검증한다는 전제**로 성격이 바뀌었습니다. 오탐을 깎는 진단 필터가 아니라
전 문장을 기록하는 커버리지 리포트여야 합니다 — 판정하지 않고 제시만 하면 "조용한 탈락" 과
"조용한 오류"(CTE 가 없는 테이블을 내는 것) 둘 다 사람이 잡을 수 있습니다. 형식은 미정입니다.
매개변수 IN 값(`I_ORD_NO`)이 빈 소스로 떨어질 때는 이제 `PARAMETER_UNRESOLVED` 가 남습니다.
`O_ERRCODE := 404` 같은 리터럴 대입은 진단을 내지 않습니다.
