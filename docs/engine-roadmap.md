# 엔진 구현 현황과 남은 작업

설계와 그 근거가 된 측정은 [engine-architecture.md](engine-architecture.md)에 있습니다.
이 문서는 **어디까지 했고 다음에 무엇을 하는가**만 다룹니다.

## 현재 상태

| 계층 | 상태 | 파일 |
|---|---|---|
| A — PL/SQL 구조 | 완료 | `parser.py`, `structure.py` |
| B — 문장 내부 (sqlglot) | Tier 0~1 범위에서 완료 (실무 코드에서 결함 2건 확인) | `sqlmap.py` |
| C — 문장 간 변수 데이터플로 | 구현·검증 완료 (B 의 구멍에 막혀 있음) | `dataflow.py` |

Tier 0~1 채점 결과입니다. 규모를 두 배로 늘려도 같습니다 — 처음 맞춘 9 파일에
과적합된 것이 아닙니다.

| | 9 패키지 / 12,059 라인 | 21 패키지 / 고유쌍 312 |
|---|---|---|
| 파싱 성공률 | 100.0% (10/10) | 100.0% (21/21) |
| 엣지 F1 | 100.0% (P 100 / R 100) | 100.0% (P 100 / R 100) |
| Kind 정확도 | 100.0% (정밀·개략) | 100.0% (정밀·개략) |
| 다홉 완주율 | 100.0% (46/46) | 100.0% (103/103) |

**이 100% 는 "엔진 완성" 이 아닙니다.** Tier 0~1 의 천장이 원래 100% 이고
(변수 경유도 동적 SQL 도 없는 구간) 거기 도달했다는 뜻입니다. 라인 비중으로 54.8% 이지만
쉬운 쪽 절반이고, 전 티어 기준으로는 A·B 만으로 다홉 완주율 48.3% 가 천장입니다.

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

즉 **다홉 완주율의 진짜 병목은 MERGE 와 CTE 입니다.** C 를 더 손봐도 그 구간이 뚫리기
전에는 다홉이 크게 오르지 않습니다.

Tier 0~1 회귀 없음 — C 적용 후에도 전 지표 100% 유지.

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

읽기 인코딩이 `utf-8` 로 고정되어 있습니다(`parser.py:96`, `engine.py:79`). 이번 자산은
전부 UTF-8 BOM 이라 통과했지만 CP949 소스는 `UnicodeDecodeError` 로 죽습니다.

### B 계층 — 새 결함 2 건

`PG_OT_ORDERS` 한 파일을 문장 단위로 계측한 결과입니다.

```
문장 104 (DML 18 / 대입 86)
엣지 원본 30 → 유지 26
탈락: 미분석 0 / 엣지0 14 / 미해결버림 4 / 대입미결 84
```

**`INSERT ... VALUES` 가 엣지를 하나도 내지 않습니다 (확인됨).** `sqlmap.py:349` 가
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

**`_alias_map` 이 `INTO` 대상을 테이블로 취급합니다 (확인됨).** sqlglot 은 `INTO V_QTY` 를
`exp.Table` 로 표현하는데 `_alias_map`(`sqlmap.py:87`)이 이를 FROM 테이블과 같이 담습니다.
한정자 없는 컬럼이 후보 테이블 2 개 사이에서 모호해져 해소에 실패합니다.

```
SELECT QTY INTO V_QTY FROM TASKDETAIL
  tables: ['V_QTY', 'TASKDETAIL']     <- V_QTY 는 변수지 테이블이 아니다
  _sources: ([], ['QTY'], [])         <- 미해결
```

이 파일의 `SELECT ... INTO` 12 건 중 8 건이 바인딩 0 개였습니다. `find_all(exp.Table)`
루프에서 `table.find_ancestor(exp.Into) is not None` 이면 건너뛰도록 하면 풀립니다.

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
막는 구멍은 `MERGE`·CTE 가 아니라 위의 두 건이었습니다.

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

## 검증되지 않은 것

- **Tier 2** — `MERGE`, CTE, 집계/분석함수, `SELECT *`, `(+)` 조인, DB 링크.
  한 번도 실행하지 않았습니다
- **전체 코퍼스 30만 라인** — 성능은 추정치(워밍업 75초 + 약 5분)일 뿐입니다
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

- **`INSERT ... VALUES` 가 엣지를 내지 않습니다 (확인됨).** `_insert` 가 `exp.Select` 가
  아니면 `return []` 하고, 주석이 가리키는 "caller" 는 존재하지 않습니다. Tier 2 시나리오
  `SELECT INTO -> INSERT ... VALUES`(`scenarios.py:893`)가 정확히 이 형태입니다.
- **`_alias_map` 이 `INTO` 대상을 테이블로 셉니다 (확인됨).** 한정자 없는 컬럼이 모호해져
  `SELECT ... INTO` 가 바인딩을 못 냅니다. C 계층이 굶는 실제 원인입니다.
- **`MERGE` 미지원.** `sqlmap._HANDLERS` 는 `Insert` / `Update` / `Delete` 뿐이라
  MERGE 는 `unhandled` 진단만 남습니다. Tier 2 의 `merge_upsert` 가 가장 흔한 시나리오이므로
  여기가 첫 작업입니다. MATCHED / NOT MATCHED 양쪽 분기를 모두 읽어야 합니다.
- **CTE 가 깨져 있습니다 (확인됨).**
  `INSERT INTO T (A) WITH c AS (SELECT s.X FROM SYN.S s) SELECT c.X FROM c` 가
  `T.A <- c.X` 를 냅니다. CTE 이름을 base table 로 취급해 **존재하지 않는 테이블 `c` 를
  소스로 지어냅니다.** 실제 소스인 `SYN.S.X` 로 뚫고 내려가야 하며, 정답셋에서 이 계보는
  `VIA_CTE` 라는 별도 kind 입니다.
- **`SELECT *` 는 엣지를 하나도 내지 않습니다 (확인됨).** 컬럼 목록을 알려면 DDL 카탈로그가
  필요합니다. 코퍼스가 `out/ddl/catalog.sql` 을 함께 생성하므로 이를 읽어 스키마를 구성해야
  합니다. 현재 엔진은 카탈로그를 전혀 읽지 않습니다.
- **`(+)` 구식 외부 조인은 문제없습니다 (확인됨).** sqlglot 이 Oracle 방언에서 파싱합니다.
- **DB 링크 `@LINK`** — 원격 객체를 어떻게 식별할지 미결. 저장 스키마 쪽 미결 사항과
  같은 문제입니다([column-lineage-schema.md](column-lineage-schema.md) 2절).

목표: Tier 2 천장은 문장 단위 완벽 엔진 기준 F1 96.7% 입니다. 그 아래는 전부 결함입니다.

### 2. C 계층 — 문장 간 변수 데이터플로

재료는 준비되어 있습니다.

- `sqlmap` 이 바인딩하지 못한 이름을 `Edge.unresolved` 로 보고합니다
- `structure` 가 `%TYPE` 앵커를 들고 있습니다 (Tier 0~1 코퍼스에서 161개)
- `structure` 가 대입문을 `assigns_to` 와 함께 소스 순서로 냅니다

해야 할 일은 서브프로그램 안에서 변수 → 값 바인딩을 순서대로 추적해,
`SELECT INTO` / `BULK COLLECT` 가 채운 변수를 뒤의 `INSERT` / `UPDATE` 가 쓸 때
두 문장을 하나의 엣지(`VIA_VARIABLE`, `hops >= 2`)로 잇는 것입니다.

주의할 점:

- 제어 흐름은 A 계층에서 이미 평탄화되어 있습니다. `IF` 안의 대입도 "그 변수가 그 값을
  **가질 수 있다**" 로 읽는 근사이며, 리니지 용도로는 타당하지만 정밀도 손실 가능성은
  Tier 2~3 에서 측정해야 합니다.
- `%ROWTYPE` 은 현재 앵커를 만들지 않습니다. 테이블은 알지만 컬럼이 특정되지 않기 때문이며,
  레코드 필드 접근(`r.ITEM_CD`)을 따라가려면 별도 처리가 필요합니다.

목표: 전 티어 다홉 완주율이 48.3% 천장을 넘어서는 것. 이 지표가 넘어가는지가
C 가 실제로 동작하는지의 유일한 증거입니다.

### 3. Tier 3

`BULK COLLECT` 와 REF CURSOR 는 C 계층과 맞물립니다. 정답셋은 REF CURSOR 투영을
`ref_cursors` 로 따로 기록하므로 채점 대상이 다릅니다.

동적 SQL 은 **잡지 않는 것이 정상**입니다. 정답셋이 `UNRESOLVED` 로 명시해 P/R 계산에서
제외하므로, 엔진은 이를 진단으로 내되 리니지를 지어내지 않아야 합니다. 현재 엔진은
`EXECUTE IMMEDIATE` 를 DML 로 보지 않아 조용히 무시합니다 — **진단으로 남기도록 고쳐야
합니다.** "해석 불가" 를 정상 출력으로 인정하는 것이 코퍼스 설계의 핵심 전제입니다.

### 4. 전체 코퍼스 실행

30만 라인을 한 번 돌려 성능 실측과 미지원 구문 분포 지도를 얻습니다. 파일들이 한 프로세스를
공유해야 DFA 캐시 이득을 봅니다.

### 5. 산출물 연결

- **뷰어** — `web/index.html` 이 읽는 `objects` / `relationships` 계약으로 내보내는
  출력 형식 추가. 현재 엔진은 정답셋 형식(`edges`)만 냅니다.
- **저장 계층** — [column-lineage-schema.md](column-lineage-schema.md) 의 3개 테이블.
  엔진 출력이 안정된 뒤의 작업입니다.

## 우선순위 요약

```
1. _alias_map 의 INTO 제외           한 줄. C 가 굶는 원인 - 실무 코드에서 확인
2. INSERT ... VALUES 핸들러          인터페이스 테이블 적재가 통째로 누락됨
3. 조용한 탈락에 진단 부여            지금은 40 개를 잃고도 진단 0 건
4. MERGE 지원 + Tier 2 채점          B 의 한계 노출, C 의 재료 확보
5. CTE 관통 (지금은 소스를 지어냄)    가장 해로운 결함 - 없는 테이블을 냄
6. SELECT * 전개 (DDL 카탈로그)      Tier 2 천장 96.7% 까지
7. C 계층 (변수 데이터플로)           완료 - 다만 1~6 이 뚫려야 효과가 큼
8. 동적 SQL 진단                     지어내지 않고 UNRESOLVED 로 남기기
9. Tier 3 / 전체 코퍼스 실행 / 뷰어 출력 형식 / 저장 계층
```

1~3 은 실무 코드 측정에서 나온 것이고 1·2 는 최소 재현까지 확인했습니다. 넣은 뒤
`synplsql.score` 로 Tier 0~1 회귀(현재 F1 100%)를 먼저 확인해야 합니다.
