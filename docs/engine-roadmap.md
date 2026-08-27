# 엔진 구현 현황과 남은 작업

설계와 그 근거가 된 측정은 [engine-architecture.md](engine-architecture.md)에 있습니다.
이 문서는 **어디까지 했고 다음에 무엇을 하는가**만 다룹니다.

## 현재 상태

| 계층 | 상태 | 파일 |
|---|---|---|
| A — PL/SQL 구조 | 완료 | `parser.py`, `structure.py` |
| B — 문장 내부 (sqlglot) | Tier 0~3 합성 코퍼스 F1 99% 이상. DB link 는 `schema.table@LINK` 로 로컬과 구분 | `sqlmap.py` |
| C — 문장 간 변수 데이터플로 | 구현·검증 완료. Tier 3 다홉 100% | `dataflow.py` |

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

Tier 3 합성 코퍼스 (변수 경유 / BULK COLLECT / REF CURSOR / 동적 SQL, 16 패키지 /
26,273 라인 / 고유쌍 342). MERGE·CTE·`SELECT *` 를 넣은 뒤 처음 잰 값입니다:

| | Tier 3 |
|---|---|
| 파싱 성공률 | 100.0% (16/16) |
| 엣지 F1 | 99.3% (P 99.1 / R 99.4) |
| Kind 정확도 | 99.4% (정밀) / 100.0% (개략) |
| 다홉 완주율 | 100.0% (162/162) |

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

같은 증상이 Windows 에서는 루트를 제대로 넘겨도 났습니다. 원인은 `--input` 이 아니라
경로 구분자였습니다 — 엔진이 `packages\X.sql` 을 내는데 manifest 는 `packages/X.sql` 이라
`score.py:192` 의 티어 조회가 전부 빗나가 `Tier -1` 로 떨어집니다. 총계는 파일과 무관하게
집계하므로 100% 로 나오고 티어별 표만 0% 가 되어, 증상만 보면 `--input` 실수와 같습니다.
`location.file` 을 POSIX 로 고정해 해결했습니다.

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

| Tier 3 | A+B | A+B+C | +결함 2건 수정 | +MERGE·CTE·`*` |
|---|---:|---:|---:|---:|
| 엣지 F1 | 76.9% | 78.6% | 79.9% | **99.3%** |
| Recall | 68.6% | 69.7% | 71.6% | **99.4%** |
| 다홉 완주율 | 33.5% | 36.1% | 43.7% | **100.0%** |

**결함 2건 수정이 C 계층 자체(+2.6)보다 다홉을 크게 올렸습니다(+7.6).** C 가 굶고 있었던
것이지 C 가 약했던 것이 아닙니다.

4 열째는 `6c6450b`·`f6b7cdd` 이후 처음 잰 값입니다. **MERGE·CTE 는 두 번째 병목이었고,
치우자 Tier 3 이 천장에 닿았습니다** — 다홉 43.7% → 100%. 위의 「놓친 것」 분해표가
`via=DERIVED` 30 건과 `VIA_CTE` 15 건을 B 책임으로 지목했던 것이 그대로 맞았습니다.
이 표의 1~3 열은 판단이 어떤 순서로 바뀌었는지를 남기기 위해 지우지 않았습니다.

**4 열은 같은 코퍼스가 아닙니다.** 1~3 열은 15 패키지 / 26,070 라인이고, 4 열은 같은
파라미터로 다시 생성한 26,273 라인 / 고유쌍 342 입니다. 티어와 규모가 같을 뿐 문장이
일대일로 대응하지는 않으므로, 4 열은 소수점 비교가 아니라 **자릿수 이동의 근거**로만
읽어야 합니다. 43.7% → 100% 는 코퍼스 차이로 설명되는 폭이 아닙니다.

Tier 0~1 회귀 없음 — C 적용 후에도, 결함 2건 수정 후에도, MERGE·CTE·`SELECT *` 이후에도
전 지표 100% 유지 (다홉 103/103).

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

## 실무 코드 재측정 (2026-08-26)

위 결함들을 고친 뒤 **같은 파일**(`PG_OT_ORDERS`, 841 라인)을 다시 넣었습니다. 08-25 와
같은 문장 단위 계측을 붙여 탈락 지점을 전수로 봤습니다.

| | 08-25 | 08-26 |
|---|---:|---:|
| 엣지 | 26 | **51** |
| `INSERT ... VALUES` 산출 | 0 (34 손실) | **22** |
| `SELECT ... INTO` 바인딩 | 12 건 중 4 건 | **47** |
| `VIA_VARIABLE` (C 계층) | 0 | **29** (hops=2) |
| 진단 | 0 | 0 |

끊겨 있던 `원천 → 인터페이스 테이블` 접합부가 이어집니다.

```
IFADM.ORDERS_IOILINK.DCCODE     <- ORDERS.CENT_CD       [VIA_VARIABLE h2]
IFADM.ORDERS_IOILINK.STORERKEY  <- ORDERS.CUST_CD       [VIA_VARIABLE h2]
IFADM.ORDERS_IOILINK.INCOTERM   <- ORDERS.TRNSP_MNS_CD  [VIA_VARIABLE h2]
```

### 남은 탈락 22 건은 전수 확인 결과 전부 정상입니다

104 문장(DML 18 / 대입 86) 을 하나씩 눈으로 판정했습니다.

| 유형 | 건수 | 판정 |
|---|---:|---|
| 리터럴 대입 (`O_ERRCODE := 404`) | 74 | 소스 없음 |
| `O_ERRMSG := '...' \|\| SQLERRM` | 8 | `SQLERRM` 은 컬럼이 아님 |
| `COUNT(*) INTO V_TEMP` | 2 | 소스 컬럼 없음 |
| `DECODE(COUNT(A.X), MAX(B.Y), 0, 1) INTO` | 2 | 결과가 리터럴 0/1. 컬럼은 분기만 결정 |
| 엣지 탈락 `I_ORD_NO` / `I_MODR_ID` | 6 | 프로시저 IN 파라미터 — 소스가 파일 밖 |
| 엣지 탈락 `V_NEW_STAT_CD` | 2 | 리터럴만 담김 |

`DECODE` 건은 `_case_conditions` 가 의도대로 동작한 결과입니다 — 검색식과 비교값은 분기를
정하고 결과값만 값을 나릅니다. **엔진이 잘못 잃는 것은 이 파일에 없습니다.**

### 조용함의 의미가 바뀌었습니다

진단은 08-25 와 똑같이 0 건입니다. 그러나 그때는 **40 개를 잘못 잃으면서** 0 건이었고
지금은 **잃는 것이 없어서** 0 건입니다. 남은 침묵은 하나뿐입니다.

```
IFADM.ORDERS_IOILINK.ORDERKEY <- I_ORD_NO   (진단 없이 사라짐)
```

파라미터 경유 6 건은 호출자를 알면 이어지는 **실재하는 리니지**인데 `engine.py` 가 소스
없는 엣지를 버리면서 흔적을 남기지 않습니다. 아래 우선순위 1 번이 잡아야 할 것은 이제
"대량 누락" 이 아니라 이 **파일 경계** 입니다.

엣지 밀도가 신호가 아니라는 근거도 강해졌습니다. 08-25 에는 30.9 대 28.7 로 구분이
안 되는 수준이었는데, 지금은 **60.6 엣지/1K 라인** 으로 합성 코퍼스(20~28)의 두 배를
넘습니다. 밀도는 어느 방향으로도 판정 근거가 되지 못합니다.

### 처리량은 그대로 문제입니다

841 라인에 63.4 초 — **13 라인/s** 입니다. 같은 실행에서 합성 코퍼스는 30,025 라인에
89.2 초로 337 라인/s 였습니다. 실무 표기가 25 배 느립니다. `plsql-lineage-engine/README.md`
의 웜 실측치(957 라인/s)는 합성 코퍼스 기준이며 실무 자산에는 적용되지 않습니다.

## 검증되지 않은 것

- **Tier 2·3** — `MERGE`, CTE, 집계/분석함수, `SELECT *`, `(+)` 조인, 변수 경유는 합성
  코퍼스 16 패키지 샘플에서 각각 100% / F1 99.3% 입니다. **한 번의 생성 샘플**이며
  규모를 늘린 재현은 Tier 0~1 에서만 했습니다. DB 링크는 `schema.table@LINK` 로 로컬
  테이블과 구분되며 엣지 `table` / `dblink` 에 보존됩니다.
- **전체 코퍼스 30만 라인** — 성능은 추정치(워밍업 75초 + 약 5분)일 뿐입니다.
  실무 표기에서는 성립하지 않는 것이 확인됐습니다(위 재측정 절, 13 라인/s)
- **실무 PL/SQL** — 1 차·2 차 측정을 했습니다(위 두 절). 다만 19,255 라인 / 13 파일이고
  전부 같은 WMS·EAI 계열이라 표기 다양성의 일부만 봤습니다. 2 차는 그중 1 파일뿐입니다.
  정답셋이 없어 P/R/F1 은 여전히 측정 불가이고, 08-26 의 "탈락 전부 정상" 판정은
  **사람이 눈으로 본 것**이지 채점이 아닙니다. 무엇을 잴 수 있고 없는지는
  [validation-limits.md](validation-limits.md)에 정리했습니다
- **12 파일 묶음 재측정** — 08-25 에 `PARSE_FAILED` 7 건이 났던 쪽은 아직 다시 넣지
  않았습니다. 그 7 건은 `CREATE OR REPLACE` 부재가 원인이라 이번 수정과 무관합니다

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

채점은 했습니다 — F1 99.3% / 다홉 100% (위 「현재 상태」). `BULK COLLECT` 와 REF CURSOR 는
C 계층과 맞물리며 정답셋이 REF CURSOR 투영을 `ref_cursors` 로 따로 기록하므로 채점 대상이
다릅니다. 남은 것은 규모를 늘린 재현과 아래 동적 SQL 진단입니다.

동적 SQL 은 **잡지 않는 것이 정상**입니다. 정답셋이 `UNRESOLVED` 로 명시해 P/R 계산에서
제외하므로, 엔진은 이를 진단으로 내되 리니지를 지어내지 않아야 합니다. `EXECUTE IMMEDIATE`
와 `OPEN ... FOR <표현식>` 은 `DYNAMIC_SQL` 진단(파일·라인·패키지·프로시저)을 남기고
SQL 문자열에서 엣지를 만들지 않습니다. 문자열 리터럴 / 변수 조립 / `USING` 바인드 여부는
메시지에 기록합니다. 런타임 로그로 동적 SQL 을 해소하는 것은 이 엔진의 범위가 아닙니다.

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
[완료] _alias_map 의 INTO 제외        360aa34 - Tier 3 다홉 36.1% -> 43.7%
[완료] INSERT ... VALUES 핸들러       360aa34 - 위와 한 묶음
[완료] C 계층 (변수 데이터플로)         dataflow.py
[완료] MERGE 지원                     MATCHED / NOT MATCHED / ON
[완료] CTE 관통                       VIA_CTE, 원천 테이블까지. recursive 는 진단
[완료] SELECT * 전개                  ddl/catalog.sql. 없으면 STAR_UNRESOLVED
[완료] 위 셋의 합                     Tier 3 다홉 43.7% -> 100%, F1 99.3%
[완료] location.file 을 POSIX 로      Windows 에서 티어별 표가 0% 로 나오던 것
[완료] 동적 SQL 진단                  EXECUTE IMMEDIATE / OPEN FOR → DYNAMIC_SQL. 엣지 없음
[완료] 빈 소스 탈락 진단              매개변수는 PARAMETER_UNRESOLVED (호출자 필요). 리터럴은 무음
[완료] CREATE 없는 ALL_SOURCE 소스    CREATE OR REPLACE 접두. 불량 소스는 PARSE_FAILED
[완료] 인코딩 utf-8 → cp949           UnicodeDecodeError 로 전체 런을 죽이지 않음
[완료] DB link 객체 식별              SYN.T@REMOTE ≠ SYN.T. 엣지에 dblink 보존

1. 조용한 탈락 커버리지 리포트        매개변수 탈락은 진단됨. 전 문장 커버리지 리포트 형식은 미정
2. 처리량                            실무 표기에서 13 라인/s. 30만 라인 추정치가 안 맞음
3. 규모 재현 / 전체 코퍼스 실행 / 뷰어 출력 형식 / 저장 계층
```

완료 항목은 모두 Tier 0~1 회귀(F1 100%, 다홉 103/103)를 확인한 뒤 반영했습니다.
남은 항목도 같은 절차를 따릅니다.

1 번은 두 번 성격이 바뀌었습니다. 처음에는 오탐을 깎는 진단 필터였고, 다음에는 **사람이
검증한다는 전제**로 전 문장 커버리지 리포트가 됐습니다. 08-26 재측정에서 한 번 더 좁혀
집니다 — `PG_OT_ORDERS` 에서 엔진이 잘못 잃는 것은 없었고, 진단 없이 사라지던 것은
`I_ORD_NO` 같은 **프로시저 파라미터 경유 6 건** 뿐이었습니다. 이것들은 결함이 아니라
파일 경계를 넘는 리니지이므로, 리포트는 "잃은 것" 이 아니라 **"여기서 끊겼고 이어붙이려면
호출자가 필요하다"** 를 내야 합니다. 매개변수 IN 값이 빈 소스로 떨어질 때는 이제
`PARAMETER_UNRESOLVED` 가 남습니다. `O_ERRCODE := 404` 같은 리터럴 대입은 진단을 내지
않습니다. 전 문장 커버리지 리포트 형식은 미정입니다.

우선순위를 이렇게 둔 이유는 합성 코퍼스가 더 알려줄 것이 거의 없기 때문입니다. Tier 0~3
이 전부 99% 이상이므로 다음 결함은 실무 자산에서만 나옵니다.
