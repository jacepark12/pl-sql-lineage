# Graphify: 인덱싱 결과를 에이전트 컨텍스트로 제공하는 방식

분석 대상: [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) `43d54ac` (기본 브랜치 `v8`, 패키지 `graphifyy` 0.9.50)
목적: 코드베이스를 그래프로 인덱싱한 뒤 **그 결과를 에이전트에게 어떻게 넣는가**를 코드로 확인하고,
본 저장소가 컬럼 계보를 에이전트에 노출할 때의 판단 근거를 남깁니다.

스키마·저장 계층의 설계 판단은 [column-lineage-for-agents.md](column-lineage-for-agents.md)에 있습니다.
이 문서는 그 위에서 **검색·투영·주입 계층**만 다룹니다.

## 1. 한 줄 결론

Graphify는 인덱스를 프롬프트에 밀어 넣지 않습니다. 디스크에 지식 그래프를 쌓고,
에이전트에게 **예산을 가진 부분 그래프를 도구로 가져오라**고 조향합니다.

벡터 저장소가 없습니다. 질의는 임베딩 최근접이 아니라
**라벨 부분문자열 + IDF + 트라이그램 후보 축소 → BFS/DFS** 입니다.
에이전트가 받는 것은 원문도 JSON 전체도 아니고, 토큰 예산으로 잘린
`NODE` / `EDGE` 텍스트입니다.

```
코드/문서
  → tree-sitter AST (+ 선택적 LLM 의미 추출)
  → graphify-out/graph.json          # 진실
  → query / path / explain / MCP     # 예산 있는 텍스트 투영
  → 에이전트 컨텍스트
```

`GRAPH_REPORT.md`와 wiki는 넓은 지도이고, 일상 질의의 기본 경로는 `graphify query` 입니다.
always-on 규칙이 그 우선순위를 강제합니다.

## 2. 인덱스가 디스크에 남기는 것

파이프라인은 `ARCHITECTURE.md` 그대로입니다.

```
detect() → extract() → build() → cluster() → analyze* → report.generate() → export
```

에이전트가 이후에 읽는 산출물은 `graphify-out/` 아래입니다.

| 산출물 | 역할 | 에이전트가 쓰는 방식 |
|---|---|---|
| `graph.json` | NetworkX node-link JSON. 노드·엣지 진실 | `query` / `path` / `explain` / MCP가 로드. 에이전트가 통째로 읽지 않음 |
| `GRAPH_REPORT.md` | god node, 커뮤니티, surprising connection, 제안 질문 | 넓은 아키텍처 리뷰, 또는 query가 부족할 때만 |
| `graph.html` | 사람이 클릭하는 시각화 | 에이전트 경로 아님 |
| `wiki/index.md` + 커뮤니티/god-node 글 | 상대 링크로 크롤 가능한 마크다운 | 있으면 원문 브라우징 대신 wiki를 탐 |
| `memory/*.md` | `save-result`가 남긴 Q&A | 다음 `--update`가 의미 추출해 그래프에 다시 심음 |
| `reflections/LESSONS.md` | `reflect`가 집계한 선호 출처·막다른 길 | 세션 시작 때 읽음 |
| `.graphify_learning.json` | 학습 오버레이. `graph.json`을 오염시키지 않는 sidecar | `NODE` 줄에 `learning=preferred` 같은 표시만 |

노드 최소 스키마 (`ARCHITECTURE.md` + `export.to_json`):

```json
{
  "id": "client_timeout",
  "label": "Timeout",
  "file_type": "code",
  "source_file": "worked/httpx/raw/client.py",
  "source_location": "L16",
  "community": 1,
  "community_name": "…",
  "norm_label": "timeout"
}
```

엣지는 `relation` (`calls` / `imports` / `uses` / …)과
`confidence` (`EXTRACTED` | `INFERRED` | `AMBIGUOUS`)를 항상 달고 있습니다.
질의 출력은 이 필드를 한 줄로 직렬화하고, **본문은 넣지 않습니다.**
인용은 `source_file` + `source_location` 포인터입니다.

## 3. 에이전트에게 도달하는 다섯 개의 표면

주입은 한 경로가 아닙니다. 같은 `graph.json`을 다섯 방식으로 읽게 만듭니다.
우선순위는 코드와 스킬이 같이 말합니다: **query → (wiki) → GRAPH_REPORT → 원문**.

### 3.1 always-on 규칙 — 그래프를 프롬프트에 넣지 않고 조향한다

`graphify install`이 호스트별로 규칙을 심습니다. Cursor 예 (`install.py`의 `_CURSOR_RULE`):

```
alwaysApply: true

Before using Read, Grep, Glob, or Bash to explore the codebase, you MUST run graphify first:
  graphify query "<question>"
  graphify path "<A>" "<B>"
  graphify explain "<concept>"
```

같은 내용이 `AGENTS.md`, `CLAUDE.md`, Gemini, Kiro, VS Code instructions에도 있습니다.
공통 문장은 이것입니다.

- 코드베이스 질문은 `graphify-out/graph.json`이 있으면 **먼저 query/path/explain**
- 그 결과가 grep/GRAPH_REPORT보다 작다
- wiki가 있으면 원문 대신 wiki
- `GRAPH_REPORT.md`는 넓은 리뷰용이거나 query가 부족할 때만
- 코드 수정 후 `graphify update .` (AST만, API 비용 없음)

**그래프 JSON은 시스템 프롬프트에 들어가지 않습니다.**
들어가는 것은 "도구를 먼저 호출하라"는 짧은 규칙입니다.
컨텍스트 윈도우를 인덱스로 채우지 않는 선택이 여기서 고정됩니다.

### 3.2 PreToolUse 훅 — grep/Read를 가로채 같은 조향을 재주입한다

규칙만으로는 에이전트가 grep으로 바로 갑니다.
Claude Code / Gemini 훅 (`cli.py` `_run_hook_guard`)이 도구 호출 직전에
`additionalContext`를 밀어 넣습니다.

검색(Bash grep / Grep 도구) 시:

> MANDATORY: graphify-out/graph.json exists. You MUST run
> `graphify query "<question>"` before grepping raw files.

원문 Read 시에도 같은 취지입니다. 그래프가 해당 파일 기준으로 stale이면
mandatory가 아니라 "읽어도 된다, 다만 update하라"로 완화됩니다.
opt-in strict 모드는 세션당 첫 Read를 `permissionDecision: deny`로 막고
query를 강제합니다. 두 번째부터는 다시 통과합니다. 에이전트를 가두지 않기 위한 상한입니다.

훅이 실패하면 조용히 통과합니다 (fail-open). 조향은 강하지만 도구를 깨지 않습니다.

### 3.3 스킬 `/graphify` — 에이전트가 파이프라인 오케스트레이터

스킬 (`tools/skillgen/fragments/core/core.md`)은 라이브러리를 직접 호출하지 않습니다.
에이전트에게 단계별 셸을 실행하라고 시킵니다. 그래프가 이미 있으면 **1–5단계를 건너뛰고 query로 점프**합니다.

빌드가 끝났을 때 에이전트가 채팅에 **붙여 넣는 것**은 보고서 전체가 아닙니다.

> paste these sections from GRAPH_REPORT.md directly into the chat:
> God Nodes / Surprising Connections / Suggested Questions
> Do NOT paste the full report

그다음 제안 질문 하나를 골라 `graphify query`로 안내합니다.
인덱스의 **하이라이트 세 덩어리**만 대화에 올리고, 나머지는 디스크에 둡니다.

의미 추출(문서/PDF/이미지)만 서브에이전트를 띄웁니다. 코드는 tree-sitter라 LLM이 필요 없습니다.
순수 코드 코퍼스는 의미 단계가 비어 있고, 토큰 비용이 0입니다.

### 3.4 CLI `query` / `path` / `explain` — 예산 있는 텍스트 부분 그래프

일상 질의의 본체입니다. CLI와 MCP가 **같은** `_query_graph_text` (`serve.py`)를 씁니다.

```
질문
  → 불용어 제거, 토큰화 (_query_terms)
  → 라벨/id/source_file에 대한 부분문자열 + IDF 점수 (_score_query)
  → seed 노드 선택 (_pick_seeds, 항당 최소 1개)
  → (선택) context_filter로 엣지 종류 축소  예: call, field
  → BFS depth=2(CLI) / 3(MCP) 또는 DFS
  → _subgraph_to_text, 기본 token_budget=2000
```

직렬화 형식:

```
Graph: graphify-out/graph.json (N nodes) | Traversal: BFS depth=2 | Start: ['APIRouter'] | Context: call | 47 nodes found

NODE APIRouter [src=routing.py loc=L2210 community=2]
NODE RequestValidationError [src=… loc=… community=…]
EDGE APIRouter --uses [INFERRED]--> RequestValidationError at=routing.py:L…
```

규칙:

- 시드 노드가 맨 위. 예산에 잘려도 질문한 심볼은 남습니다.
- 나머지는 시드로부터의 홉, 그다음 차수.
- 문자 예산은 `token_budget * 3`.
- 잘리면 맨 위에 `[!] TRUNCATED: showing X of Y nodes` — 침묵을 부재로 읽지 못하게.
- 노드는 다 들어가고 엣지만 넘치면 잘라내지 않고, 예산 초과를 정직히 알립니다.
- LLM이 만든 필드는 `sanitize_label`을 통과합니다 (프롬프트 인젝션, ANSI).
- 학습 sidecar가 있으면 `learning=preferred:stale` 같은 접미사.

`explain`은 한 노드의 이웃을 방향·관계·confidence·호출 위치와 함께 최대 20개 찍고,
나머지는 파일별로 묶습니다. 고차수 god node에서 "누가 호출하는가"가 `... and 80 more`로 사라지지 않게 하기 위한 처리입니다.

`path`는 최단 경로를 홉 단위로 찍습니다. 기본은 저장 방향을 존중하고 `--undirected`로 풀 수 있습니다.

스킬은 질의 전에 에이전트에게 `graph.json` 라벨에서 `.vocab.txt`를 뽑고,
질문과 의미적으로 맞는 토큰을 **그 목록에서만** 최대 12개 고르라고 합니다.
바이너리 질의는 어간·동의어·교차언어가 없기 때문입니다.
확장 토큰은 사용자에게 먼저 공개됩니다. 발명 금지가 하드 제약입니다.

### 3.5 MCP 서버 — 같은 투영을 도구로

`graphify serve` (`serve.py` `_build_server`)가 stdio/HTTP로 도구를 노출합니다.
반환 타입은 전부 `TextContent` 문자열입니다. JSON 블롭이 아닙니다.

| 도구 | 하는 일 |
|---|---|
| `query_graph` | 위와 동일한 BFS/DFS 텍스트 |
| `get_node` | 라벨/ID 한 노드의 id, source, type, community, degree |
| `get_neighbors` | 직접 이웃. `relation_filter`, `token_budget` |
| `get_community` | 커뮤니티 전체 노드 목록 (예산 절단) |
| `god_nodes` | 최고 차수 노드 |
| `graph_stats` | 노드/엣지/커뮤니티/confidence 집계 |
| `shortest_path` | 두 개념 사이 최단 경로 |
| `list_prs` / `get_pr_impact` / `triage_prs` | PR이 건드리는 커뮤니티·blast radius |

리소스 URI는 넓은 지도를 게으르게 읽게 합니다.

- `graphify://report` — `GRAPH_REPORT.md` 전문
- `graphify://god-nodes`, `://surprises`, `://questions`, `://audit`, `://stats`

모든 도구에 `project_path`를 붙일 수 있어 한 서버가 여러 `graph.json`을 LRU로 캐시합니다.
기본 그래프는 pin, 나머지는 용량 8 (`GRAPHIFY_MAX_CONTEXTS`).

## 4. 질의 결과를 다시 인덱스로 넣는 루프

질의는 읽기만 하지 않습니다.

1. 에이전트가 답한 뒤 `graphify save-result --question … --answer … --nodes … --outcome useful|dead_end|corrected`
2. `graphify-out/memory/query_<ts>_<slug>.md`에 YAML frontmatter + 본문으로 저장 (`ingest.save_query_result`)
3. 다음 `--update`가 이 마크다운을 의미 추출해 그래프 노드로 심음
4. `graphify reflect`가 memory를 집계해 `reflections/LESSONS.md`를 씀
   - preferred sources (여러 `useful`로 뒷받침된 노드)
   - known dead ends
   - corrections
5. 세션 시작 때 스킬이 `reflect --if-stale` 후 `LESSONS.md`를 읽으라고 함
6. 같은 집계가 `.graphify_learning.json` sidecar로도 나가, query/explain 출력에 display-only로 붙음

구조적 진실(`graph.json`)과 경험적 진실(학습 sidecar)을 분리합니다.
학습 필드가 그래프에 다시 쓰이지 않습니다.

## 5. 의도적으로 에이전트에게 주지 않는 것

이 선택이 설계의 핵심입니다.

| 주지 않는 것 | 대신 주는 것 |
|---|---|
| `graph.json` 전체 | seed 주변 부분 그래프, 기본 ~2000 토큰 |
| 소스 파일 본문 | `src=` + `loc=` 포인터. 수정/디버그는 그다음 Read |
| 임베딩 / top-k 청크 | 설명 가능한 엣지 (`calls` `imports` `uses` + confidence) |
| 잘림을 숨긴 짧은 답 | 상단 TRUNCATED 배너와 좁히는 힌트 (`context_filter`, `get_node`) |
| 동의어 자동 확장 | 그래프 어휘에서만 고르는 에이전트 측 확장 |
| 학습 신호를 그래프에 각인 | sidecar + `LESSONS.md` |

벤치마크 모듈 (`benchmark.py`)이 이 계약을 숫자로 잽니다.
코퍼스 토큰 대비 질의 서브그래프 토큰. Graphify의 가치가 "더 많이 넣기"가 아니라
**질문당 컨텍스트를 작게 유지하기**라는 뜻입니다.

## 6. 본 저장소에 대한 함의

[column-lineage-for-agents.md](column-lineage-for-agents.md)의 결론은
매핑이 주소 가능해야 하고, 응답 크기를 투영으로 제한해야 한다는 것이었습니다.
Graphify는 그 계약을 **코드 심볼 그래프에서 이미 구현한 사례**입니다.

가져올 패턴:

- **진실은 디스크, 컨텍스트는 투영.** 에이전트 프롬프트에 계보 JSON을 넣지 말 것.
  `graphify query`에 해당하는 `lineage query "<column>"` / `path A B`가 기본 표면.
- **한 줄 직렬화 + 토큰 예산 + 상단 절단 고지.** 침묵한 절단은 에이전트가 부재로 읽습니다.
- **포인터로서의 span.** Graphify는 `source_file`/`source_location`만 줍니다.
  본 스키마의 `span` + `evidenceRef`와 같은 방향입니다. SQL 전문은 키로 빼고 필요할 때 읽기.
- **조향은 짧고 항상 켜 둘 것.** always-on 규칙 + (가능하면) grep/Read 훅.
  스키마가 좋아도 에이전트가 grep으로 새면 투영 계층은 존재하지 않은 것과 같습니다.
- **confidence를 엣지에 실어 출력에 그대로 노출.** EXTRACTED/INFERRED/AMBIGUOUS는
  본 스키마의 `method`/`confidence`/`status`와 대응합니다. 에이전트가 "읽은 것"과
  "추론한 것"을 구분할 수 없으면 인용 가치가 없습니다.
- **MCP 도구 단위는 노드·이웃·경로·커뮤니티.** OpenMetadata `get_entity_lineage`처럼
  테이블 엣지 블롭을 기본값으로 주지 않습니다. 컬럼 매핑은 `get_node` 급의
  주소 지정 조회가 기본이어야 합니다.

가져오지 말 것 / 여기 없는 것:

- Graphify SQL extractor (`extractors/sql.py`)는 테이블·뷰·함수와 `references` 엣지입니다.
  **컬럼 계보가 아닙니다.** 대체재가 아니라 한 계층 위의 지도입니다.
- 노드 granularity가 심볼(함수/클래스)입니다. 컬럼 매핑은 그보다 한 단계 더 곱습니다.
  기본 BFS depth 2–3을 컬럼 그래프에 그대로 쓰면 넓은 테이블에서 예산이 바로 찹니다.
  `context_filter`에 해당하는 **kind 필터** (`direct` / `filter` / `join`)가 처음부터 질의 API에 있어야 합니다.
- 어휘 확장은 Graphify가 자유 텍스트 라벨을 쓰기 때문에 필요합니다.
  계보 식별자가 FQN이면 리터럴 매칭이 더 잘 맞고, 동의어 우회는 오히려 독입니다.
- `save-result` 루프는 대화형 코드 탐색에는 맞습니다. 계보 정답 루프는
  `status: proposed|accepted|rejected`와 `supersedes`가 그 자리를 이미 차지하므로
  Q&A 문서를 다시 추출하는 우회는 필요 없습니다.

OpenMetadata 분석과 맞물리면 한 문장입니다.

> 저장은 주소 가능한 assertion, 노출은 예산 있는 부분 그래프 텍스트, 주입은 조향이지 덤프가 아니다.
