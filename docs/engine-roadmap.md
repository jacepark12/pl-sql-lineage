# 엔진 구현 현황과 남은 작업

설계와 그 근거가 된 측정은 [engine-architecture.md](engine-architecture.md)에 있습니다.
이 문서는 **어디까지 했고 다음에 무엇을 하는가**만 다룹니다.

## 현재 상태

| 계층 | 상태 | 파일 |
|---|---|---|
| A — PL/SQL 구조 | 완료 | `parser.py`, `structure.py` |
| B — 문장 내부 (sqlglot) | Tier 0~1 범위에서 완료 | `sqlmap.py` |
| C — 문장 간 변수 데이터플로 | **미착수** | — |

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

## 검증되지 않은 것

한 번도 실행하지 않았습니다. 아래는 추정이 아니라 **미측정**입니다.

- **Tier 2** — `MERGE`, CTE, 집계/분석함수, `SELECT *`, `(+)` 조인, DB 링크
- **Tier 3** — 커서 루프, `BULK COLLECT`, REF CURSOR, `CONNECT BY`, `PIVOT`, 동적 SQL
- **전체 코퍼스 30만 라인** — 성능은 추정치(워밍업 75초 + 약 5분)일 뿐입니다
- **실무 PL/SQL** — 합성 코퍼스는 렌더러가 만들어 포맷이 균일합니다. ANTLR 문법 자체는
  실제 Oracle 을 보고 쓰인 것이라 일반화가 기대되지만 확인된 바 없습니다

## 남은 작업

### 1. Tier 2 로 범위 확대 — 우선순위 1

아래 구멍은 짧은 SQL 을 엔진에 직접 넣어 확인한 것이며, 추정이 아닙니다.

Tier 2 를 먼저 하는 이유는 두 가지입니다. B 의 실제 한계가 드러나고, 동시에 변수 경유와
다문장 전이가 처음 등장해 **C 를 검증할 재료가 생깁니다.** C 를 먼저 만들면 Tier 0~1 에는
변수 경유가 없어 점수가 움직이지 않고, 검증 없이 코드만 쌓입니다.

알려진 구멍:

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
1. MERGE 지원 + Tier 2 채점          B 의 한계 노출, C 의 재료 확보
2. CTE 관통 (지금은 소스를 지어냄)    가장 해로운 결함 - 없는 테이블을 냄
3. SELECT * 전개 (DDL 카탈로그)      Tier 2 천장 96.7% 까지
4. C 계층 (변수 데이터플로)           다홉 48.3% 천장 돌파가 유일한 증거
5. 동적 SQL 진단                     지어내지 않고 UNRESOLVED 로 남기기
6. Tier 3 / 전체 코퍼스 실행
7. 뷰어 출력 형식, 저장 계층
```
