# 에이전트 리니지 컨텍스트 계약

목적: 엔진이 뽑은 컬럼 엣지를 **에이전트 프롬프트에 덤프하지 않고**, FQN으로 주소 지정한 부분 그래프만 짧은 텍스트로 준다.

저장 granularity의 판단은 [column-lineage-for-agents.md](column-lineage-for-agents.md)에 있다.
Graphify가 같은 주입 패턴을 코드 심볼 그래프에서 쓰는 방식은
[graphify-agent-context.md](graphify-agent-context.md)에 있다(그 문서가 아직 없으면
[Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) `serve.py`의
`_subgraph_to_text`가 원본이다). 이 문서는 **이 저장소의 조회 계약**만 적는다.

구현: `plsqllineage.agent` (그래프·직렬화), `python3 -m plsqllineage.query` (CLI).

## 1. 한 줄

진실은 엔진 `edges` JSON에 두고, 에이전트에게는 시드 컬럼의 **상류 부분 그래프**를
`COL` / `EDGE` / `DIAG` 줄로 준다. 소스 본문은 넣지 않는다. 인용은 `file:line`이다.

```
PL/SQL  →  engine.json  →  query / explain / path  →  예산 있는 텍스트  →  에이전트
                                                         ↓
                                                 필요하면 원문 Read
```

사람은 `web/index.html` (뷰어 JSON). 에이전트는 이 CLI. 둘의 소스 오브 트루스는
엔진 `edges`이다. `export.to_viewer`를 에이전트에 물리지 않는다.

## 2. 고정한 결정

- **백엔드:** 엔진 JSON. sqlite/Postgres 리뷰 워크플로는 전제가 아니다.
  `store.sources_for`는 유지하고, 같은 질의 API 뒤로 나중에 갈아끼운다.
- **매칭:** FQN·부분 FQN. 동의어·IDF·vocab 확장 없음.
  `ORD_QTY` / `OUT_ALLOC.ORD_QTY` / `SYNWMS.OUT_ALLOC.ORD_QTY`.
  0건이면 후보 FQN을 최대 8개 제시하고 멈춘다. 2건 이상이면 ambiguous.
- **방향:** 기본 상류(sources). `--downstream`으로 하류.
- **kind:** 기본 `value` =
  `DIRECT` `TRANSFORM` `AGGREGATE` `ANALYTIC` `VIA_VARIABLE` `VIA_CTE` `VIA_PIPELINE`.
  `INDIRECT_FILTER`는 `FILTER`로 접는다. `--kind FILTER` / `--kind all`.
  시드에 붙은 `UNRESOLVED`/`SEVERED`는 필터와 무관하게 항상 보인다.
- **출력:** 본문 없음. `expr=` + `at=` + `method=`. 절단은 상단 `[!] TRUNCATED`.
  시드 `COL` 줄은 잘려도 남긴다. 문자 예산은 `token_budget * 3`.
- **1차에 없는 것:** MCP, PreToolUse 훅, wiki, save-result, 임베딩,
  에이전트 쓰기(`proposed`/`supersedes`).

컬럼 그래프는 심볼 그래프보다 촘촘하다. 그래서 kind 필터를 1차부터 켠다.
테이블 단위 필터(`target.column == null` → `TABLE.*`)는 `--kind FILTER`일 때만
해당 테이블 컬럼 질의의 추가 시드가 된다.

## 3. CLI

```sh
python3 -m plsqllineage.engine --input <sql-or-corpus> --out /tmp/engine.json

python3 -m plsqllineage.query --input /tmp/engine.json SYNWMS.OUT_ALLOC.ORD_QTY
python3 -m plsqllineage.query --input /tmp/engine.json --kind FILTER OUT_ALLOC.ORD_QTY
python3 -m plsqllineage.query --input /tmp/engine.json --downstream --depth 1 Client
python3 -m plsqllineage.query --input /tmp/engine.json explain IF_STOCK_SND.QTY
python3 -m plsqllineage.query --input /tmp/engine.json path OUT_ORDER_D.ORD_QTY OUT_ALLOC.ORD_QTY
python3 -m plsqllineage.query --input /tmp/engine.json diagnose
```

`--input`이 없으면 엔진을 먼저 돌리라고만 하고 끝낸다. JSON을 지어내지 않는다.

| 명령 | 역할 |
|---|---|
| `query COL` | 시드에서 상류 N홉 (기본 depth 2, budget 2000) |
| `explain COL` | 1홉. 20개를 넘으면 파일별로 묶는다 |
| `path A B` | 값 흐름 방향(source → target)의 최단 경로. 같은 노드면 에러 |
| `diagnose` | `diagnostics` + 시드 없는 `UNRESOLVED` 엣지. 동적 SQL 우선 |

## 4. 텍스트 계약

```
Column: SYNWMS.OUT_ALLOC.ORD_QTY
  Upstream depth=2 kind=value  |  1 assertions  |  budget ~2000

COL SYNWMS.OUT_ALLOC.ORD_QTY
COL SYNWMS.OUT_ORDER_D.ORD_QTY
EDGE DIRECT SYNWMS.OUT_ORDER_D.ORD_QTY --> SYNWMS.OUT_ALLOC.ORD_QTY
     expr=d.ORD_QTY  at=packages/SYNWMS.PKG_OUT_004.sql:42 PKG_OUT_004.SP_ALLOC_QTY  method=static-parse
DIAG SQL_NOT_ANALYZED at=packages/SYNWMS.PKG_OUT_004.sql:55 PKG_OUT_004.SP_ALLOC_QTY  "sqlglot could not parse statement"
```

`UNRESOLVED` 시드:

```
EDGE UNRESOLVED (unresolved) --> SYNWMS.STK_TRX.TRX_QTY
     expr=EXECUTE IMMEDIATE v_sql  at=packages/SYNWMS.PKG_STK_006.sql:120 ...
DIAG UNRESOLVED at=...  "EXECUTE IMMEDIATE v_sql"
```

같은 프로시저의 `diagnostics`는 서브그래프에 동봉한다. 다른 파일의 `PARSE_FAILED`는
그 컬럼 질의에 실지 않는다.

에이전트는 이 텍스트만으로 답하고, 수정·디버그가 필요하면 `at=`를 따라 원문을 읽는다.

## 5. 조향

`edges` JSON을 시스템 프롬프트에 넣지 않는다. 루트 [`AGENTS.md`](../AGENTS.md)와
[`.cursor/rules/lineage.mdc`](../.cursor/rules/lineage.mdc)가 컬럼/테이블 질문을
grep보다 `plsqllineage.query`에 보낸다. 추출 오케스트레이션 스킬은 없다.
빌드는 기존 `plsqllineage.engine`이다.

## 6. 이후

- MCP `query_lineage` / `get_column` / `shortest_path` — 이 모듈의 `render_*` 재사용
- sqlite 어댑터 — `status='accepted'` 뷰가 필요할 때
- 에이전트 쓰기 — [column-lineage-schema.md](column-lineage-schema.md)의 `proposed`/`supersedes`
- grep 훅 — always-on 규칙이 새는 것이 관측된 뒤
