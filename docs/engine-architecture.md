# 리니지 엔진 구현 계획 — 난이도 티어와 3계층 구조

현재 저장소에는 SQL을 파싱하는 코드가 없습니다(커밋 `9dff998` 에서 Java 분석기가 제거되었고,
`score.py` 와 `web/index.html` 은 입력을 만들어 줄 엔진을 기다리는 상태입니다).
이 문서는 그 엔진을 다시 만들 때의 **구조 결정과 그 근거가 된 측정**을 기록합니다.

숫자는 전부 합성 코퍼스에서 측정했고 재현 방법은 5절에 있습니다. 실제 운영 자산이 아니라
그 구문 분포를 재현한 합성 코퍼스라는 점을 감안해 읽으십시오.

## 1. 난이도 티어

합성 코퍼스는 패키지마다 **난이도 등급 하나**를 붙이고 그 등급에 허용된 구문만 사용합니다.
등급은 `manifest.json` 에 기록됩니다.

```json
{
  "file": "packages/SYNWMS.PKG_IFC_001.sql",
  "package": "SYNWMS.PKG_IFC_001",
  "tier": 0,
  "lines": 339,
  "scenarios": ["insert_simple", "update_simple"]
}
```

| Tier | 포함 구문 | 라인 비중 | 용도 |
|---|---|---:|---|
| **0** | 단순 `INSERT ... SELECT`, 단일 테이블, 컬럼 1:1 | 14.9% | 파서 스모크 테스트 |
| **1** | 다중 조인, `CASE` / `DECODE`, `NVL`, 명시적 컬럼목록 | 39.9% | 기본 정확도 측정 |
| **2** | `MERGE`, CTE, 집계/분석함수, `SELECT *`, `(+)` 조인, DB 링크 | 34.9% | 실전 수준 |
| **3** | 커서 루프, `BULK COLLECT`, REF CURSOR, `CONNECT BY`, `PIVOT`, 동적 SQL | 10.3% | 한계 시험 |

배분은 패키지 개수가 아니라 **라인 수** 기준입니다. 개수로 나누면 큰 패키지가 한 티어에
몰려 라인 비중이 틀어지고, 실제로 Tier 3가 한 개도 생성되지 않은 적이 있습니다
([plsql-lineage-corpus/docs/PLAN.md](../plsql-lineage-corpus/docs/PLAN.md) 회고 참조).

### 티어별 실물

**Tier 0** — 컬럼 대응이 자명합니다.

```sql
INSERT INTO SYNWMS.OUT_ALLOC (WH_CD, ORD_NO, LINE_NO, ITEM_CD, ALLOC_QTY)
SELECT d.WH_CD, d.ORD_NO, d.LINE_NO, d.ITEM_CD, d.ORD_QTY
  FROM SYNWMS.OUT_ORDER_D d;
```

**Tier 1** — 표현식과 조인이 붙어 대응이 더 이상 자명하지 않습니다.

```sql
SELECT /*+ LEADING(d) */
       NVL(TRIM(d.WH_CD), '-')                                    AS WH_CD,
       CASE WHEN d.LINE_STAT_CD = '10' THEN d.ORD_NO ELSE ' ' END AS ORD_NO,
```

**Tier 2** — 서브쿼리 안에서 별칭을 풀어야 합니다.

```sql
MERGE INTO SYNIF.IF_STOCK_SND t
USING ( SELECT /*+ USE_HASH(s w) */ ...
          FROM SYNWMS.STK_ONHAND s LEFT JOIN SYNWMS.MST_WAREHOUSE w ON ... ) 
```

**Tier 3** — 값이 SQL 문장 밖으로 나갑니다. 커서, 컬렉션, REF CURSOR, 동적 SQL.

### 선택 생성

개발 초기에는 필요한 티어만 빠르게 생성합니다.

```sh
python3 -m synplsql.generate --tier 0,1 --packages 20 --lines 30000 --out out/dev
```

## 2. 측정 — sqlglot 이 어디까지 하는가

### 2.1 패키지 전체는 못 읽습니다

`sqlglot.parse(text, dialect="oracle")` 에 패키지 파일을 통째로 넣으면 패키지 스펙에서
바로 실패합니다. PL/SQL 은 sqlglot 의 대상이 아닙니다.

### 2.2 문장 단위로는 SQL 을 전부 읽습니다

생성기 IR 에서 문장을 하나씩 렌더해 넣은 결과입니다(sqlglot 30.17.0, 40 패키지).

| 문장 타입 | 정상 파싱 | 에러 |
|---|---:|---:|
| `InsertSelect` `InsertValues` `Update` `Merge` `Delete` `SelectInto` | **100%** | 0 |
| `IfBlock` `CursorLoop` `ForLoop` `ForAll` `OpenRefCursor` | **0%** | 전부 |

경계가 선명합니다 — **SQL 은 sqlglot 이 전부 처리하고, PL/SQL 제어 구조는 하나도 처리하지
않습니다.** 티어별 정상률이 75% 근처로 고르게 나오는 것은 난이도 차이가 아니라 각 티어에
섞인 PL/SQL 제어문의 비율 때문입니다.

> **함정.** sqlglot 은 못 읽어도 예외를 던지지 않고 `Command` 노드로 조용히 폴백합니다.
> `try/except` 만으로 성공률을 세면 부풀려집니다. `EXECUTE IMMEDIATE` 가 대표적입니다.
> 측정 코드는 `isinstance(tree, exp.Command)` 를 따로 셉니다.

### 2.3 `sqlglot.lineage()` 는 절반만 줍니다

값 계보는 잘 나옵니다. `SUM(NVL(d.ORD_QTY, 0)) AS ALLOC_QTY` 에서
`ALLOC_QTY <- SYNWMS.OUT_ORDER_D.ORD_QTY` 를 표현식까지 보존해 돌려줍니다.

그러나 **`WHERE` / `JOIN` / `GROUP BY` 필터 엣지는 나오지 않습니다.** 정답셋에서
`INDIRECT_FILTER` 는 2,888건, 전체의 33% 입니다. AST 가 있으므로 직접 훑으면 되는
작업이지만, `lineage()` 를 부르는 것만으로 끝나지 않는다는 점은 계획에 반영해야 합니다.

또 `lineage()` 는 `SELECT` 를 받으므로 `INSERT ... SELECT` 는 벗겨서 넣어야 하고,
컬럼 하나씩 호출하는 구조입니다.

## 3. 측정 — 문장 단위 분석의 천장

정답셋에서 **문장 경계를 넘는 엣지를 제거**하고, 남은 것만 완벽하게 찾아내는
가상의 엔진(오답 0건)을 채점기에 넣었습니다. 이 점수를 넘는 문장 단위 엔진은
존재할 수 없습니다.

```
엣지 Precision   100.0%     (가정상 당연)
엣지 Recall       89.3%
엣지 F1           94.4%
다홉 완주율       48.3%     (1,950 체인 중 942)

Tier 0  F1 100.0%      Tier 2  F1  96.7%
Tier 1  F1 100.0%      Tier 3  F1  59.6%   (Recall 42.5%)
```

도달하지 못하는 1,359건(15.7%)의 내역입니다.

| 원인 | 건수 | 비중 |
|---|---:|---:|
| PL/SQL 변수 경유 | 763 | 8.8% |
| 다문장 전이 (변수 없이) | 470 | 5.4% |
| 동적 SQL (원리적 불가) | 126 | 1.5% |

원인은 변수 경유를 먼저 귀속시킵니다. 변수를 타고 3홉 이상 간 엣지는 다문장 전이가 아니라
변수 경유로 셉니다 — 근본 원인이 그쪽이기 때문입니다.

### "문장 경계를 넘는다" 가 무슨 뜻인가

값이 SQL 문장 **두 개 이상**에 걸쳐 흐른다는 뜻입니다. 코퍼스의 실제 코드입니다
(`packages/SYNWMS.PKG_MST_010.sql`, `SP_SYNC_OUT_STOCK`).

```sql
-- 문장 ①
SELECT ... CASE WHEN r.IF_STAT_CD = '10' THEN r.UNIT_WGT ELSE 0 END AS UNIT_WGT ...
  BULK COLLECT INTO t_rows                    -- 테이블에서 꺼내 PL/SQL 컬렉션에 담음
  FROM SYNIF.IF_ITEM_RCV r;

-- 문장 ②
FORALL i IN 1 .. t_rows.COUNT
  UPDATE SYNWMS.MST_ITEM t
     SET t.UNIT_WGT = t_rows(i).UNIT_WGT      -- 그 컬렉션을 꺼내 다른 테이블에 씀
   WHERE t.ITEM_CD = t_rows(i).ITEM_CD;
```

정답은 엣지 하나입니다 — `SYNIF.IF_ITEM_RCV.UNIT_WGT -> SYNWMS.MST_ITEM.UNIT_WGT`,
`kind: VIA_VARIABLE`, `hops: 2`.

한 번에 문장 하나씩만 보면 이렇게 보입니다.

| | 보이는 것 | 문제 |
|---|---|---|
| 문장 ① | `IF_ITEM_RCV.UNIT_WGT` -> `t_rows` | `t_rows` 는 테이블이 아님. **도착지가 없음** |
| 문장 ② | `t_rows` -> `MST_ITEM.UNIT_WGT` | `t_rows` 는 테이블이 아님. **출발지가 없음** |

두 문장 다 문법적으로 완벽하고 sqlglot 도 문제없이 읽습니다. 둘을 잇는 `t_rows` 가 SQL
객체가 아니라 PL/SQL 변수일 뿐입니다. 문장 사이에서 **`t_rows` 에 무엇이 담겼는지 기억**해야
이어 붙일 수 있고, 그것이 C 계층이 하는 일입니다.

세 유형의 차이는 이렇습니다.

- **변수 경유**(763) — 위 예시. `SELECT INTO` / `BULK COLLECT` 로 변수에 담고 뒤에서 씁니다.
- **다문장 전이**(470) — 변수 없이 테이블을 거칩니다. `A -> B` 문장과 `B -> C` 문장이
  따로 있고, `A -> C` 를 알려면 둘을 합성해야 합니다.
- **동적 SQL**(126) — `EXECUTE IMMEDIATE v_sql`. 객체명이 실행 시점에 정해지므로
  정적 분석으로는 **원리적으로 불가**합니다. 정답셋이 `UNRESOLVED` 로 명시해 채점에서
  제외하는 이유입니다.

앞 둘은 구현하면 잡히고, 마지막은 못 잡는 것이 정상입니다.

**핵심은 F1 이 아니라 다홉 완주율입니다.** 문장 단위로 완벽해도 절반을 못 넘습니다.
체인은 링크 하나만 끊겨도 실패합니다.

```
SRC_ITEM_MST.ITM_CODE -> IF_ITEM_RCV.ITEM_CD -> MST_ITEM.ITEM_CD -> ... -> RPT_DAILY_STK
                                              ^
                                     여기 한 곳이 VIA_VARIABLE 이면
                                     체인 전체가 끊긴다
```

엣지 기준으로는 8.8% 만 놓쳤는데 다홉 완주율이 48.3% 로 떨어지는 이유가 이것입니다.
개별 엣지를 대부분 맞혀도 "이 리포트 값이 원래 어느 시스템에서 왔나" 에는 답하지 못합니다.
F1 94.4% 는 위안이 되지 않습니다.

## 4. 구조 — 3계층

측정이 가리키는 구조는 하나입니다.

```
A. PL/SQL 구조 스캐너
     패키지·서브프로그램 경계, 선언부, 문장 범위, 변수 대입
     기성품이 없는 유일한 부분
        │
        ▼
B. sqlglot (문장별)
     값 계보 + 필터 엣지(AST 직접 훑기)
     구 MVP 가 손수 만든 쿼리 분석기로 가장 크게 졌던 지점
        │
        ▼
C. 문장 간 변수 데이터플로
     SELECT INTO -> 변수 -> INSERT 를 이어 붙임
     VIA_VARIABLE 과 다홉 전이를 생성
```

### C 를 미루면 안 되는 이유

3절의 숫자가 그 이유입니다. C 없이는 다홉 완주율 48.3% 가 천장이고, 그것이 실사용
정확도에 가장 가까운 지표입니다. 제거된 Java MVP 가 엣지 F1 70.7% 인데 다홉 완주율
23.6% 로 무너진 것도 같은 구조적 이유입니다.

C 는 나중에 붙이기 가장 어려운 계층이기도 합니다. A 와 B 가 문장을 독립적으로 처리하도록
굳어지면, 문장 사이의 상태를 나중에 끼워 넣기 위해 둘 다 손봐야 합니다.

### B 에서 이길 여지

구 MVP 의 F1 70.7% 를 만든 것은 손수 만든 쿼리 분석기였고, 그 영역이 정확히 sqlglot 이
100% 처리하는 구간입니다. B 를 sqlglot 에 넘기는 것만으로 상당한 개선이 기대됩니다.

### 언어

Python 을 권합니다. sqlglot, 코퍼스 생성기, 채점기가 모두 Python 이고
`score.py --format generic` 이 바로 붙습니다. Java 로 가면 그 다리를 다시 놓아야 합니다.

### 시작 범위

`--tier 0,1` 이 자연스럽습니다. 두 가지 이유입니다.

1. 20 패키지 3만 라인이면 되므로 반복이 빠릅니다.
2. **Tier 0~1 은 문장 단위 완벽 엔진 기준 모든 지표가 100% 입니다.** 여기서 점수가 안
   나오면 원인이 A 나 B 의 결함으로 특정됩니다. 엔진의 버그와 설계의 천장이 섞이지 않습니다.

`--tier 0,1` 로 생성한 코퍼스에 3절의 측정을 그대로 돌린 결과입니다.

```
엣지 F1        100.0%
다홉 완주율    100.0%   (46/46)
UNRESOLVED     0건
```

전 티어에서 48.3% 였던 다홉 완주율이 여기서는 100% 입니다. Tier 0~1 에는 변수 경유도
동적 SQL 도 없기 때문입니다. 바꿔 말하면 **이 구간에서 다홉이 100% 가 아니면 그것은 전부
구현 결함**입니다.

단, Tier 0~1 만 보면 **C 의 필요성이 드러나지 않습니다.** 변수 경유와 다홉 전이는 주로
Tier 2~3 에 몰려 있습니다. 골격은 Tier 0~1 에서 세우되 C 를 빼고 시작하지는 마십시오.

### A 계층 — 미결

직접 스캐너와 ANTLR PL/SQL 문법 중 무엇으로 갈지는 정해지지 않았습니다.

A 가 실제로 필요한 것은 서브프로그램 범위, 선언부, 문장 범위, 변수 대입뿐이고 문장 내부는
sqlglot 이 처리하므로, 완전한 PL/SQL 문법이 없어도 성립합니다. 반대로 실무 코드의 기괴한
구문(중첩 블록, `q'[...]'` 문자열)에서는 스캐너가 취약합니다. A 를 인터페이스로 격리해
두면 나중에 교체할 수 있고, B·C 는 A 의 구현과 무관하게 재사용됩니다.

## 5. 재현

```sh
cd plsql-lineage-corpus && python3 -m synplsql.generate --out out
pip install sqlglot          # 2절에만 필요. 3절은 없어도 동작
python3 ../scripts/measure_parser_ceiling.py --out out
```

`scripts/measure_parser_ceiling.py` 가 2절과 3절을 모두 출력합니다. sqlglot 은 아직
저장소의 의존성이 아닙니다 — 측정용으로만 썼습니다.
