# OpenMetadata Column-Level Lineage 분석

분석 대상: [open-metadata/OpenMetadata](https://github.com/open-metadata/openmetadata)
기준 커밋: `56d99af` (2026-08-20), 버전 `2.0.0-SNAPSHOT`
목적: 컬럼 단위 계보 기능의 데이터 모델, 추출 방식, 저장/조회 구조, 정확도의 실제 수준을 확인하고
본 저장소의 PL/SQL 분석기 설계에 반영할 지점을 정리합니다.

## 1. 한 문장 요약

OpenMetadata의 컬럼 계보는 **독립된 그래프가 아니라 테이블 간 엣지에 붙는 부속 속성**이며,
추출은 대부분 **SQL 텍스트 파싱**(collate-sqllineage의 3개 파서 폴백)에 의존하고,
조회는 **검색 엔진에 비정규화한 엣지 문서를 계층 BFS로 훑는 방식**입니다.
결과적으로 "빠르고 넓게 붙지만, 컬럼 단위 정확도는 파서에 종속되고 변환식은 보존하지 않는" 구조입니다.

## 2. 스키마 타입 카탈로그

계보 관련 타입은 JSON Schema(draft-07)로 정의되고, 빌드 시 Java POJO와 TypeScript 인터페이스로
동시 생성됩니다. `javaType`이 명시된 정의는 그 FQCN으로, 명시가 없는 중첩 정의는 같은 패키지에
정의 이름의 파스칼케이스로 생성됩니다.

### 2.1 코어 계보 타입 — `type/entityLineage.json`

| 타입 | 생성 Java 타입 | 역할 |
|---|---|---|
| `columnLineage` | `o.o.schema.type.ColumnLineage` | **컬럼 계보 최소 단위**. N:1 매핑 1건 |
| `lineageDetails` | `o.o.schema.type.LineageDetails` | 엣지에 붙는 부속 정보 묶음. `columnsLineage`를 품음 |
| `edge` | `o.o.schema.type.Edge` | 엣지(UUID 식별). `lineageDetails` 포함 |
| `entitiesEdge` | `o.o.schema.type.EntitiesEdge` | 엣지(EntityReference 식별). 쓰기 API용 |
| `tempLineageTable` | `o.o.schema.type.TempLineageTable` | 임시 테이블 경유 1홉 `{fromEntity, toEntity}` |
| (최상위) | `o.o.schema.type.EntityLineage` | 특정 엔티티 기준 계보 그래프 응답 |

필드 상세:

```jsonc
// ColumnLineage — 컬럼 계보의 유일한 단위 타입
{
  "fromColumns": [ fullyQualifiedEntityName ],   // 배열, 필수 아님(스키마상)
  "toColumn":      fullyQualifiedEntityName,     // 단수
  "function":      sqlFunction                   // 선택
}

// LineageDetails — 엣지 부속 정보
{
  "sqlQuery":          sqlQuery,
  "columnsLineage":  [ ColumnLineage ],
  "pipeline":          EntityReference,          // pipeline 또는 storedProcedure
  "description":       string,
  "source":            LineageSource,            // 열거형, 기본 "Manual"
  "createdAt":         timestamp,  "createdBy": string,
  "updatedAt":         timestamp,  "updatedBy": string,
  "assetEdges":        integer,                  // ChildAssets 계보의 자산 수
  "tempLineageTables": [ TempLineageTable ]
}

// Edge vs EntitiesEdge — 식별 방식만 다른 쌍둥이
Edge         { fromEntity: uuid,            toEntity: uuid,            description, lineageDetails }
EntitiesEdge { fromEntity: EntityReference, toEntity: EntityReference, description, lineageDetails }
```

`Edge`/`EntitiesEdge` 모두 `additionalProperties: false`이고 `fromEntity`/`toEntity`만 필수입니다.
`ColumnLineage`와 `LineageDetails`에는 필수 필드가 하나도 없습니다. 즉 **스키마 수준에서는
`toColumn` 없는 `ColumnLineage`도 유효**하고, 걸러내는 일은 5.2의 서버 검증 로직이 담당합니다.

### 2.2 기반 스칼라 타입 — `type/basic.json`

| 정의 | 타입 | 제약 | 계보에서의 쓰임 |
|---|---|---|---|
| `fullyQualifiedEntityName` | string | 1–3072자 | 컬럼 식별자. `svc.db.schema.table.column` |
| `sqlQuery` | string | — | `lineageDetails.sqlQuery` |
| `sqlFunction` | string | — | `columnLineage.function` |
| `uuid` | string(uuid) | — | `Edge`의 엔드포인트 |
| `timestamp` | integer | epoch millis | 엣지 생성/수정 시각 |

여기서 `sqlFunction`의 설명이 설계 의도를 드러냅니다: *"SQL function. Example - `AVG()`, `COUNT()`"*.
즉 `function`은 **완전한 변환식이 아니라 함수 이름을 담으려던 필드**입니다. 전체 표현식
(`CASE WHEN ... END`, `a * b + c`)을 담기에는 애초에 의도된 그릇이 아니고, 실제로도
SAP HANA 파서 한 곳만 채웁니다(4.6 참조).

컬럼 식별이 UUID가 아니라 **FQN 문자열**이라는 점이 이 스키마의 가장 큰 구조적 선택입니다.
컬럼은 독립 엔티티가 아니라 테이블 엔티티의 하위 필드이므로 자체 ID가 없고, 그래서 계보가
문자열 참조로만 성립합니다. 5.4의 리네임 추종 코드는 이 선택의 대가입니다.

### 2.3 API 요청/응답 타입 — `api/lineage/*.json`

| 스키마 파일 | 생성 타입 | 방향 | 비고 |
|---|---|---|---|
| `addLineage.json` | `AddLineageRequest` | 쓰기 | `{ edge: EntitiesEdge }` 단일 필드 |
| `searchLineageRequest.json` | `SearchLineageRequest` | 읽기 | `columnFilter`, `preservePaths`, 시간창 |
| `searchLineageResult.json` | `SearchLineageResult` | 읽기 | 노드/엣지를 **Map**으로 반환 |
| `nodeInformation.json` | `NodeInformation` | 읽기 | `{ entity: Map<String,Object>, paging, nodeDepth }` |
| `esLineageData.json` | `EsLineageData` | 색인 | 검색 문서에 박히는 엣지 표현 |
| `lineageDirection.json` | `LineageDirection` | 공통 | `Upstream` \| `Downstream` |
| `entityCountLineageRequest.json` | `EntityCountLineageRequest` | 읽기 | 테이블 모드 영향분석 페이징 |
| `lineagePaginationInfo.json` | `LineagePaginationInfo` | 읽기 | 깊이별 엔티티 수 |
| `hydrateLineageRequest.json` | `HydrateLineageRequest` | 읽기 | 노드 상세 일괄 조회 |
| `hydrateLineageResponse.json` | `HydrateLineageResponse` | 읽기 | `entitiesByType`, `droppedCount` |

`SearchLineageResult`의 형태가 특징적입니다.

```jsonc
{
  "nodes":          Map<String /*FQN*/, NodeInformation>,
  "upstreamEdges":  Map<String /*docUniqueId*/, EsLineageData>,
  "downstreamEdges":Map<String /*docUniqueId*/, EsLineageData>,
  "paginationInfo": LineagePaginationInfo
}
```

배열이 아니라 맵입니다. 중복 제거와 클라이언트 측 조인을 위해 `existingJavaType`으로
`java.util.Map`을 직접 지정했습니다. `NodeInformation.entity`도 타입이 아니라
`Map<String, Object>`입니다 — 즉 **노드 본문은 스키마로 타입화하지 않고 통째로 흘려보냅니다.**
엔티티 종류가 20종 이상이라 유니온을 만드는 대신 택한 절충입니다.

### 2.4 열거형 정리

| 열거형 | 정의 위치 | 값 |
|---|---|---|
| `LineageSource` | `entityLineage.json` (인라인) | `Manual`, `ViewLineage`, `QueryLineage`, `PipelineLineage`, `DashboardLineage`, `DbtLineage`, `SparkLineage`, `OpenLineage`, `ExternalTableLineage`, `CrossDatabaseLineage`, `ChildAssets` (11종, 기본 `Manual`) |
| `LineageDirection` | `api/lineage/lineageDirection.json` | `Upstream`, `Downstream` |
| `LineageLayer` | `configuration/lineageSettings.json` | `EntityLineage`, `ColumnLevelLineage`, `DataObservability` |
| `PipelineViewMode` | `configuration/lineageSettings.json` | `Edge`, `Node` |
| `QueryParserType` | `metadataIngestion/parserconfig/queryParserConfig.json` | `Auto`, `SqlGlot`, `SqlFluff` |

`LineageSource`는 삭제 단위이기도 합니다. `deleteLineageBySource`가 이 값으로 엣지를 일괄
삭제하므로, 재수집 시 낡은 계보를 걷어내는 유일한 열쇠입니다(5.3 참조).

### 2.5 설정 타입

| 스키마 | 생성 타입 | 계보 관련 필드 |
|---|---|---|
| `configuration/lineageSettings.json` | `LineageSettings` | `upstreamDepth`/`downstreamDepth` (1–5, 기본 2), `lineageLayer`, `pipelineViewMode`, `graphPerformanceConfig` |
| 〃 | `GraphPerformanceConfig` | `smallGraphThreshold` 5000, `mediumGraphThreshold` 50000, `maxInMemoryNodes` 100000, `cacheTTLSeconds` 300, `useScrollForLargeGraphs` |
| `metadataIngestion/parserconfig/queryParserConfig.json` | `QueryParserConfig` | `type: QueryParserType` |
| `.../automator/lineagePropagationAction.json` | `LineagePropagationAction` | `propagateColumnLevel`(기본 true), `propagateTags`, `propagateGlossaryTerms`, `propagationFilterMode: SOURCE\|TARGET` |
| `metadataIngestion/databaseServiceQueryLineagePipeline.json` | — | `processViewLineage`, `processQueryLineage`, `processStoredProcedureLineage`, `enableTempTableLineage`, `processCrossDatabaseLineage`, `overrideViewLineage`, `parsingTimeoutLimit` |

계보 조회 기본 깊이가 **상·하류 각 2단계**이고 최대 5로 제한된다는 점이 중요합니다.
UI의 컬럼 추적(7절)은 로드된 서브그래프 안에서만 BFS하므로, 이 깊이 제한이 곧
**컬럼 추적의 실질 한계**가 됩니다.

### 2.6 같은 컬럼 계보의 세 가지 표현

동일한 정보가 계층마다 다른 그릇에 담깁니다. 손실 지점이 여기서 갈립니다.

| 계층 | 그릇 | 보존되는 것 | 잃는 것 |
|---|---|---|---|
| 저장 / 쓰기 API | `LineageDetails.columnsLineage: ColumnLineage[]` | 전부 | — |
| 검색 색인 / 읽기 API | `EsLineageData.columns: ColumnLineage[]` | N:1 그룹핑, FQN | — (같은 타입을 `$ref`로 재사용) |
| CSV 내보내기 | `"fromFqn:toFqn;fromFqn:toFqn"` 평면 문자열 | 쌍 관계 | **N:1 그룹핑**, `function`, `source` |

`EsLineageData`는 `columns` 필드에서 `entityLineage.json#/definitions/columnLineage`를
그대로 `$ref` 하므로 **저장과 색인이 동일한 생성 타입을 공유**합니다. 반면 CSV는
`LineageRepository.processColumnLineage`가 `fromColumn:toColumn;` 으로 평탄화하므로
`fromColumns` 3개짜리 매핑 1건이 독립된 쌍 3개로 흩어집니다. 왕복(export → import)에서
"세 컬럼이 함께 하나를 만든다"는 정보가 소실됩니다.

`EsLineageData`가 코어 타입과 다른 점은 엔드포인트 표현입니다. `EntityReference` 대신
경량 `relationshipRef`(`id`, `fullyQualifiedName`, `fqnHash`, `type`)를 쓰고,
반복되는 SQL은 `sqlQueryKey`로 부모 문서의 `lineageSqlQueries` 맵을 참조합니다.
검색 문서 크기를 줄이려는 최적화입니다.

### 2.7 컬럼을 가질 수 있는 엔티티

컬럼 계보의 양 끝이 될 수 있는 엔티티는 UI 기준 8종입니다
(`ui/src/constants/Lineage.constants.ts:137`).

| 엔티티 | 하위 필드 이름 |
|---|---|
| Table | `columns` |
| Dashboard, DashboardDataModel | `charts` / `columns` |
| MlModel | `mlFeatures` |
| Container | `dataModel.columns` |
| Topic | `messageSchema.schemaFields` |
| SearchIndex | `fields` |
| ApiEndpoint | `requestSchema` / `responseSchema` |

서버의 `getChildrenNames`(`LineageRepository.java:1141`)가 엔티티 타입별로 분기해
하위 필드 이름 집합을 만들고, 중첩 구조(struct)는 재귀 전개합니다. 즉 **컬럼 계보는
관계형 테이블 전용이 아니라 "하위 필드를 갖는 모든 엔티티"에 일반화**되어 있습니다.

### 2.8 설계 요약

1. 컬럼 계보에 **독립 엔티티도, 독립 테이블도, 독립 API도 없습니다.** 오직 `ColumnLineage` 한
   타입이 `LineageDetails` 안에 배열로 들어갈 뿐입니다.
2. 식별은 전적으로 **FQN 문자열**입니다. 최대 3072자 제약이 유일한 형식 검증입니다.
3. **필수 필드가 없어** 스키마 검증이 사실상 무력하고, 실질 검증은 전부 서버 런타임 로직입니다.
4. **직접/간접 구분, 신뢰도, 소스 위치를 담을 필드가 없습니다.** 확장하려면 스키마 변경이 필요하며,
   `additionalProperties: false`라 우회 삽입도 막혀 있습니다.
5. `function`은 "함수 이름"을 의도한 필드이고 사실상 미사용입니다.

## 3. 전체 파이프라인

```text
[1] 추출 (Python, ingestion)
    쿼리 로그 / 뷰 정의 / 커넥터 API
      -> LineageParser (SqlGlot -> SqlFluff -> SqlParse 폴백)
      -> (raw column pair) -> FQN 해소 -> ColumnLineage[]
      -> AddLineageRequest (PUT /v1/lineage)

[2] 저장 (Java, openmetadata-service)
    LineageRepository.addLineage
      -> validateLineageDetails: 실존하지 않는 컬럼 매핑 제거
      -> entity_relationship 테이블 (relation=UPSTREAM, json=lineageDetails)

[3] 색인
    각 엔티티 문서에 upstreamLineage[] 비정규화 (columns[] 포함)

[4] 조회
    GET /v1/lineage/getLineage?fqn=...&columnFilter=...
      -> 검색 엔진 계층 BFS -> columnFilter 인메모리 매칭 -> preservePaths 보정

[5] UI (React Flow)
    테이블 노드 = 컨테이너, 컬럼 = 노드 내부 행(Handle)
      -> column edge = sourceHandle/targetHandle 로 연결
      -> 컬럼 클릭 시 BFS 로 상·하류 컬럼 경로 하이라이트
```

## 4. 추출 계층 — 파서 3중 폴백

### 4.0 의존성 실체: sqlglot을 직접 쓰지 않고 sqllineage를 거쳐 씁니다

혼동하기 쉬운 지점이라 먼저 분명히 합니다. OpenMetadata가 `setup.py`에 선언하는
SQL 파싱 의존성은 **단 하나**입니다.

```python
# ingestion/setup.py:181
"collate-sqllineage==2.1.4",
```

`sqlglot`, `sqlfluff`, `sqlparse`는 전부 이 패키지를 통해 **전이적으로** 딸려옵니다.
`collate-sqllineage 2.1.4`의 배포 메타데이터가 세 백엔드를 정확한 버전으로 못 박습니다.

```text
Requires-Dist: sqlglot==29.0.1
Requires-Dist: collate-sqlfluff==3.5.3     # sqlfluff 역시 Collate 포크
Requires-Dist: sqlparse==0.5.4
Requires-Dist: networkx>=2.4
```

저장소 전체에서 `import sqlglot` 형태의 직접 임포트는 **한 건도 없습니다.** 접근 경로는
언제나 sqllineage의 어댑터 클래스입니다.

```python
# ingestion/src/metadata/ingestion/lineage/parser.py:26-30
from collate_sqllineage import SQLPARSE_DIALECT
from collate_sqllineage.core.parser.sqlfluff.analyzer import SqlFluffLineageAnalyzer
from collate_sqllineage.core.parser.sqlglot.analyzer  import SqlGlotLineageAnalyzer
from collate_sqllineage.core.parser.sqlparse.analyzer import SqlParseLineageAnalyzer
from collate_sqllineage.runner import LineageRunner
```

`collate-sqllineage`는 Collate(OpenMetadata 상용사)가 관리하는 **`sqllineage`의 포크**입니다.
두 패키지를 나란히 열어 보면 차이가 분명합니다.

| | 파서 백엔드 |
|---|---|
| 원본 `sqllineage` 1.5.8 | `sqlfluff`, `sqlparse` |
| 포크 `collate-sqllineage` 2.1.4 | `sqlfluff`, `sqlparse`, **`sqlglot`** |

즉 **sqlglot 백엔드는 포크에서 추가된 것**이고, 그것이 현재 OpenMetadata의 1순위 파서입니다.
따라서 층위는 이렇습니다.

```text
OpenMetadata (LineageParser)
    └── collate-sqllineage (LineageRunner + Analyzer 추상화, 계보 그래프 구성)
            ├── sqlglot 29.0.1        <- AST 백엔드 1 (dialect 인지, 포크에서 추가)
            ├── collate-sqlfluff 3.5.3 <- AST 백엔드 2 (dialect 인지)
            └── sqlparse 0.5.4         <- 토큰 기반 백엔드 3 (dialect 무시)
```

정리하면:

- **"OpenMetadata가 sqlglot을 쓴다"는 맞습니다** — 단, 직접 API를 호출하는 게 아니라
  sqllineage 포크의 백엔드 중 하나로 씁니다.
- 계보 로직(테이블/컬럼 그래프 구성, `get_column_lineage()`)은 **sqlglot이 아니라 sqllineage**에
  있습니다. sqlglot은 AST를 만들어 줄 뿐입니다.
- 따라서 8절의 정확도 문제는 sqlglot 자체의 파싱 능력 문제라기보다,
  **sqllineage의 각 백엔드용 계보 추출 어댑터 구현 차이**에서 나옵니다.
  같은 쿼리를 세 백엔드에 넣었을 때 결과가 갈리는 이유가 여기 있습니다.
- 사용자는 인제스천 파이프라인 설정에서 `QueryParserType`으로 백엔드를 강제할 수 있습니다
  (`Auto` | `SqlGlot` | `SqlFluff`). `SqlParse`는 선택지에 없고 항상 최후 폴백으로만 동작합니다.

### 4.1 폴백 순서와 채택 기준

`ingestion/src/metadata/ingestion/lineage/parser.py`

```python
# _evaluate_best_parser_impl 의 실제 순서
SqlGlot   (dialect 적용, timeout 30s)  -> 성공하면 채택
SqlFluff  (dialect 적용, timeout 30s)  -> 성공하면 채택
SqlParse  (dialect 무시, 최후 폴백)     -> 성공하면 채택
모두 실패 -> None (계보 없음)
```

판정 기준은 "예외 없이 `get_column_lineage()`가 끝나는가"이고, **결과의 품질은 비교하지 않습니다.**
SqlGlot이 부실한 결과 1건을 반환해도 그것이 채택되고 SqlFluff는 아예 시도되지 않습니다.
쿼리 해시에 `-SqlGlot` / `-SqlFluff` / `-SqlParse` 접미사를 붙여 어떤 파서가 채택됐는지 로그로만 남깁니다.

dialect는 커넥션 타입에서 매핑합니다(`lineage/models.py`). Oracle은 `Dialect.ORACLE`로 매핑되어
있고, 지원 dialect는 25종입니다. 다만 이는 **SQL dialect**이지 PL/SQL 문법이 아닙니다.

### 4.2 중간 컬럼을 버리는 축약

```python
# parser.py, column_lineage
for col_lineage in self.parser.get_column_lineage():
    src_column = col_lineage[0]    # 맨 앞
    tgt_column = col_lineage[-1]   # 맨 뒤
    # 그 사이 CTE/서브쿼리 중간 컬럼은 폐기
```

sqllineage는 `src -> cte1.col -> cte2.col -> tgt` 같은 경로 전체를 주는데, OpenMetadata는
양 끝만 취합니다. 결과적으로 **CTE·서브쿼리를 거친 계보는 "원천 → 최종"으로 평탄화**됩니다.
탐색 UX에는 유리하지만, 어느 중간 단계에서 값이 변형됐는지는 복원 불가능합니다.

### 4.3 FQN 해소와 `SELECT *`

`ingestion/src/metadata/ingestion/lineage/sql_lineage.py`

```python
# get_column_lineage
if "*" in column_lineage_map[to_table][from_table][0]:
    column_lineage_map[to_table][from_table] = [
        (c.name.root, c.name.root) for c in from_entity.columns
    ]
...
to_col_fqn   = get_column_fqn(to_entity, to_col)
from_col_fqn = get_column_fqn(from_entity, from_col)
if to_col_fqn and from_col_fqn:      # 양쪽 다 실제 존재해야만 채택
    column_lineage.append(ColumnLineage(fromColumns=[from_col_fqn], toColumn=to_col_fqn))
```

- `SELECT *`는 **소스 테이블의 컬럼 이름을 그대로 타깃에 1:1 매핑**합니다. 카탈로그에 이미
  수집된 컬럼 목록에 의존하므로, 메타데이터 수집이 선행되지 않으면 컬럼 계보가 통째로 비어 있습니다.
- 컬럼 매칭은 **대소문자 무시 이름 일치**입니다(`get_column_fqn`, `sql_lineage.py:70`).
  타입·순서·위치 정보는 쓰지 않습니다.
- 양쪽 FQN 중 하나라도 해소되지 않으면 그 매핑은 조용히 버려집니다. 진단으로 남지 않습니다.

### 4.4 임시 테이블 체인에서 컬럼 계보가 소실됨

`enableTempTableLineage`를 켜면 임시 테이블을 노드로 하는 networkx DiGraph를 누적하고,
마지막에 실체 테이블 쌍만 뽑아 엣지를 만듭니다(`get_lineage_by_graph`). 그런데 이 경로는:

```python
# _get_lineage_for_path -> _build_table_lineage(...)
column_lineage_map={},        # 항상 빈 딕셔너리
masked_query=None,
```

즉 **임시 테이블을 경유해 이어붙인 엣지에는 컬럼 계보가 하나도 붙지 않습니다.** 경유 경로는
`tempLineageTables`에 테이블 이름 수준으로만 기록됩니다. 다홉 컬럼 추적이 필요한 사용자에게는
이 지점이 가장 큰 실질적 한계입니다.

### 4.5 저장 프로시저 계보는 "본문 파싱"이 아니라 "실행 로그 상관"

이 프로젝트와 직접 대비되는 부분입니다. OpenMetadata는 프로시저 본문을 파싱해 계보를 뽑지 않습니다.
런타임 쿼리 이력에서 프로시저 호출 구간과 시간이 겹치는 DML을 골라 그 프로시저의 것으로 귀속시킵니다.

Oracle 구현(`ingestion/src/metadata/ingestion/source/database/oracle/queries.py:263`):

```sql
WITH SP_HISTORY AS (          -- gv$sql 에서 CALL / BEGIN 문
  SELECT sql_text, FIRST_LOAD_TIME .. LAST_LOAD_TIME + ELAPSED_TIME, PARSING_SCHEMA_NAME
  FROM gv$sql WHERE UPPER(sql_text) LIKE '%CALL%' OR UPPER(sql_text) LIKE '%BEGIN%'
),
Q_HISTORY AS (                -- gv$sql 에서 그 외 DML
  SELECT ... FROM gv$sql WHERE sql_text NOT LIKE '%CALL%' AND NOT LIKE '%BEGIN%'
)
SELECT ... FROM SP_HISTORY SP JOIN Q_HISTORY Q
  ON Q.start_time BETWEEN SP.start_time AND SP.end_time
 AND Q.end_time   BETWEEN SP.start_time AND SP.end_time
 AND Q.user_name = SP.user_name
 AND Q.QUERY_TYPE <> 'SELECT'
```

**같은 사용자 + 시간 구간 포함**이 유일한 귀속 근거입니다. 같은 계정이 동시에 다른 배치를 돌리면
오귀속이 발생합니다. 그리고 프로시저 계보를 지원하는 커넥터는 5개뿐입니다:
BigQuery, MSSQL, Oracle, Redshift, Snowflake.

의미하는 바:

- 실행되지 않은 프로시저는 계보가 없습니다. 배포는 됐지만 아직 안 돈 코드, 분기 때문에 이번 달에
  안 탄 경로는 전부 누락됩니다.
- `gv$sql`은 라이브러리 캐시라 에이징으로 사라집니다. `queryLogDuration`을 길게 잡아도 실제로는
  캐시에 남아 있는 것만 봅니다.
- 반대로 정적 파싱이 못 하는 것 — 동적 SQL의 실제 실행 형태 — 은 이 방식이 잡아냅니다.

> 참고로 OpenMetadata 자체 감사 체크리스트(`skills/connector-audit/prompts/04-lineage.md`)도
> 이 점을 명시합니다: "static analysis of definitions (e.g., parsing procedure body SQL) IS
> implementable and can be rated ⚠️ if missing, but runtime lineage without a source system data
> source is N/A." 즉 프로시저 본문 정적 분석은 **미구현 갭으로 인지하고 있는** 항목입니다.

### 4.6 파싱 외 경로

파싱에 의존하지 않고 컬럼 계보를 만드는 커넥터들이 따로 있습니다. 정확도는 이쪽이 훨씬 높습니다.

| 방식 | 대표 구현 | 비고 |
|---|---|---|
| 원천 시스템 네이티브 계보 | Snowflake `ACCESS_HISTORY` (`snowflake/lineage.py:480`), Unity Catalog, Databricks | 컬럼 쌍을 그대로 받아 FQN만 해소 |
| 표준 프로토콜 | OpenLineage (`pipeline/openlineage/metadata.py:805`), Spline, Fivetran | 컬럼 facet 수신 |
| 모델 메타데이터 | dbt (`dbt/metadata.py:1710`), Looker, Tableau, PowerBI, Superset | 모델/필드 정의에서 도출 |
| 전용 파서 | SAP HANA calculation view XML (`saphana/cdata_parser.py`) | 유일하게 `function`(수식)까지 보존 |
| 이름 일치 | cross-database, external table (`lineage_source.py:469`) | 같은 이름 컬럼을 그대로 연결 |

## 5. 저장 계층

### 5.1 물리 저장

`LineageRepository.addLineage` (`openmetadata-service/.../jdbi3/LineageRepository.java:271`)는
`entity_relationship` 테이블 한 행으로 저장합니다.

```
(fromId, toId, fromEntity, toEntity, relation=UPSTREAM, json=<lineageDetails 전체>)
```

**컬럼 계보 전용 테이블이 없습니다.** 컬럼 매핑 전체가 하나의 JSON 컬럼 안에 들어갑니다.
따라서 "이 컬럼을 참조하는 모든 엣지"를 관계형으로 질의할 수 없고, 그래서 6절의 검색 엔진
비정규화가 필수가 됩니다.

### 5.2 서버 측 검증 — 실존하지 않는 컬럼은 조용히 제거

`validateLineageDetails` (`LineageRepository.java:718`):

```java
Set<String> fromColumns = getChildrenNames(from);   // 실제 엔티티의 컬럼 목록
Set<String> toColumns   = getChildrenNames(to);
for (ColumnLineage cl : columnsLineage) {
    if (!toColumns.contains(strip(cl.getToColumn())))  continue;   // 통째로 폐기
    // fromColumns 중 존재하지 않는 것 제거
    // 남은 fromColumns 가 비면 매핑 폐기
}
```

중첩 컬럼(struct)도 `getChildrenNames`가 재귀 전개하므로 지원됩니다. 다만 필터링 결과는
`LOG.debug`로만 남고 API 응답에 경고가 들어가지 않습니다. **보낸 컬럼 매핑이 사라져도
클라이언트는 알 수 없습니다.**

### 5.3 갱신 의미 — 서버는 덮어쓰기, 클라이언트는 합집합

- 서버 `addLineage`는 `relationshipDAO().insert(...)`로 **JSON 전체를 교체**합니다.
- 인제스천 클라이언트는 `check_patch=True`일 때 기존 엣지를 GET 해서 `_merge_column_lineage`로
  **합집합**을 만든 뒤 PATCH 합니다(`ometa/mixins/lineage_mixin.py:192`).

```python
union_result = flat_original_result.union(flat_updated_result)
return [{"fromColumns": list(t[:-1]), "toColumn": t[-1]} for t in union_result]
```

두 가지 부작용이 있습니다.

1. **단조 증가**입니다. 쿼리에서 컬럼 매핑이 사라져도(리팩터링으로 더 이상 안 쓰는 매핑) 제거되지
   않습니다. `overrideLineage` 옵션으로 원천 단위 전체 삭제 후 재작성을 해야 정리됩니다.
2. `(fromColumns..., toColumn)` 튜플만 집합에 넣으므로 **`function` 필드는 병합 과정에서 유실**됩니다.

### 5.4 스키마 변경 추종

`updateColumnLineage` (`LineageRepository.java:1766`)는 테이블의 컬럼이 rename/삭제될 때
해당 테이블이 걸린 UPSTREAM 관계 행을 모두 읽어 `columnsLineage` 안의 FQN을 재작성하거나 제거합니다.
`fromColumns`가 전부 비면 매핑 자체를 삭제합니다. 컬럼 계보를 FQN 문자열로 들고 있는 설계의
필연적인 유지보수 코드입니다.

## 6. 조회 계층 — 검색 엔진 비정규화

각 엔티티의 검색 문서에 **자기 자신의 상류 엣지 배열**을 통째로 복사해 넣습니다
(`search/indexes/LineageIndex.java`, 매핑은 `table_index_mapping.json`).

```jsonc
"upstreamLineage": {
  "properties": {
    "fromEntity": { "fullyQualifiedName", "fqnHash" },
    "toEntity":   { "fullyQualifiedName", "fqnHash" },
    "columns":    { "fromColumns": text/keyword, "toColumn": text/keyword },
    "sqlQueryKey": "keyword",     // 중복 SQL 은 부모 문서의 lineageSqlQueries 맵 참조
    "source", "createdAt", "updatedAt", ...
  }
}
```

그래프 순회는 재귀 SQL이 아니라 **깊이마다 검색 질의 1회**로 계층 확장(BFS)합니다.
`lineageSettings.json`에 성능 파라미터가 노출돼 있습니다(smallGraphThreshold 5000,
mediumGraphThreshold 50000, maxInMemoryNodes 100000, 캐시 TTL 300초, 대형 그래프는 scroll API).

### 6.1 컬럼 필터

`searchLineageRequest.json`의 `columnFilter`는 `"type:value"` 콤마 구분 문법입니다
(`search/ColumnFilterMatcher.java`).

```
columnName:customer_id          # 컬럼 이름
tag:PII.Sensitive               # 컬럼에 붙은 태그
glossary:BusinessGlossary.Term  # 용어
columnName:email,tag:PII        # 같은 타입끼리 OR, 다른 타입끼리 AND
```

주의할 점: 매핑의 `columns`가 ES `nested` 타입이 **아니라** 평범한 object 배열이라
`fromColumns`/`toColumn` 쌍 단위 질의가 검색 엔진 쪽에서 불가능합니다. 그래서 필터는
**결과를 받아온 뒤 자바 힙에서 재매칭**합니다. 태그·용어 필터는 `ColumnMetadataCache`로
컬럼 메타데이터를 추가 조회해서 판정합니다. 즉 컬럼 필터는 검색 최적화가 아니라 후처리입니다.

### 6.2 preservePaths

`preservePaths=true`(기본)면 필터에 걸린 노드에서 루트까지의 경로를 역추적해 중간 노드를
되살립니다(`search/LineagePathPreserver.java`). 필터링 때문에 그래프가 끊겨 보이는 것을 막는 장치입니다.
단, 시간 창(`startTime`/`endTime`) 필터에는 적용되지 않습니다. 스키마 주석이 이를 명시합니다:
시간 창은 순회 중 하드 프루닝이라 창 밖 엣지 하나가 그 너머 전체의 발견을 끊습니다.

### 6.3 API 표면

`/v1/lineage` 아래 주요 엔드포인트(`resources/lineage/LineageResource.java`):

| 엔드포인트 | 용도 |
|---|---|
| `GET /getLineage` | FQN 기준 검색 기반 계보 (columnFilter 지원) |
| `GET /getLineage/{direction}` | 방향별 페이지네이션 조회 |
| `GET /getLineageEdge/{fromId}/{toId}` | 단일 엣지 상세(컬럼 매핑 포함) |
| `GET /export`, `/exportAsync` | CSV 내보내기 (컬럼 매핑을 문자열로 직렬화) |
| `PUT /` , `PUT /{fromEntity}/name/...` | 엣지 추가/갱신 |
| `POST /hydrate` | 노드 상세 일괄 조회 (N회 왕복 제거) |
| `GET /getDataQualityLineage` | DQ 오버레이 |

## 7. UI 계층

`ui/src/utils/EntityLineageEdgeUtils.ts`, `context/LineageProvider/LineageProvider.tsx`

- 컬럼 레이어는 토글입니다(`lineageLayer: EntityLineage | ColumnLevelLineage | DataObservability`).
  꺼져 있으면 컬럼 엣지를 아예 만들지 않습니다(`createEdgesAndEdgeMaps`).
- 컬럼 엣지 id: `column-{fromColumnFqn}-{toColumnFqn}-edge-{sourceNodeId}-{targetNodeId}`.
  React Flow의 `sourceHandle`/`targetHandle`에 **컬럼 FQN을 그대로 넣습니다.**
  테이블 노드가 컨테이너, 컬럼이 그 안의 행(Handle)인 구조로, 본 저장소 `web/index.html`의
  중첩 노드 렌더링과 같은 접근입니다.
- `columnsHavingLineage: Map<nodeId, Set<columnFqn>>`를 만들어 "계보가 있는 컬럼만 보기"
  필터와 노드 내 컬럼 검색을 지원합니다(`NodeChildren.component.tsx:83`). 컬럼이 수백 개인
  테이블에서 그래프가 무너지는 것을 막는 실용적 장치입니다.
- 컬럼 선택 시 하이라이트는 클라이언트 BFS입니다(`getAllTracedColumnEdge` → `getAllTracedEdges`).
  `sourceHandle`/`targetHandle` 일치로 상·하류를 각각 큐 순회해 연결된 컬럼 집합을 만듭니다.
  즉 **화면에 로드된 서브그래프 안에서만** 추적되며, 깊이를 넘어가면 끊깁니다.
- 편집 모드에서 컬럼 핸들끼리 드래그하면 `columnsLineage`에 항목을 추가해 PUT 합니다
  (`source: Manual`). 수동 보정이 정식 경로로 지원됩니다.

## 8. 정확도의 실제 수준

OpenMetadata 자신의 테스트가 가장 정직한 증거입니다.
`ingestion/tests/unit/lineage/queries/`의 두 파일에는 **181건의 컬럼 계보 단언**이 있고,
각 단언은 파서별로 켜고 끌 수 있게 되어 있습니다. 실제 비활성화 현황:

| 파서 | 테이블 계보 단언에서 제외 | 컬럼 계보 단언에서 제외 |
|---|---|---|
| SqlGlot | 22 / 181 (12%) | 74 / 181 (41%) |
| SqlFluff | 41 / 181 (23%) | 73 / 181 (40%) |
| SqlParse | 22 / 181 (12%) | 59 / 181 (33%) |

**컬럼 단위 추출은 테이블 단위 대비 파서 취약성이 3배 이상**입니다. 그리고 세 파서 중
어느 것도 40% 가까운 케이스에서 기대값을 맞추지 못합니다. 주석에 남은 실패 사유가 구체적입니다.

```python
# test_merge_upsert_operation
# SqlGlot: Creates additional incorrect column lineage
#          tgt.total_purchases -> target_customers.total_purchases
test_sqlglot=False

# test_insert_with_complex_union
# SqlGlot: Not generating any column lineage
```

즉 **오탐(잘못된 엣지 생성)과 미탐(엣지 없음)이 둘 다** 나오며, 4.1의 "첫 파서 성공 시 채택"
정책과 결합하면 어떤 파서가 걸리느냐에 따라 결과가 달라집니다. 취약 구문은 테스트 이름에서
드러납니다: MERGE, UNION을 포함한 INSERT, CTE와 결합한 UPDATE, 5단계 중첩 CTE,
상관 서브쿼리, GROUPING SETS/ROLLUP/CUBE, 재귀 CTE.

## 9. 정리 — 강점과 한계

**강점**

- 스키마가 단순합니다. 컬럼 계보가 엣지의 부속 속성이라 API·저장·색인 전 계층이 한 모델로 통일됩니다.
- 파서 폴백 + 타임아웃 + 예외 격리로 **한 쿼리 실패가 워크플로를 죽이지 않습니다.**
  대량 쿼리 로그를 다루는 시스템의 현실적 선택입니다.
- 검색 엔진 비정규화로 대규모 그래프 순회가 깊이당 질의 1회로 끝납니다.
- 컬럼 rename/삭제 시 계보 FQN 재작성, 실존 컬럼 검증, 수동 보정 등 **운영 유지보수 경로**가 갖춰져 있습니다.
- 파싱 외에 네이티브 계보(Snowflake ACCESS_HISTORY), 표준 프로토콜(OpenLineage), 모델 메타데이터(dbt)
  경로를 병행해 정확도가 중요한 원천은 파싱을 우회합니다.

**한계**

| 한계 | 위치 | 영향 |
|---|---|---|
| 변환식 미보존 | SQL 파싱 경로 전체 | "어떻게 만들어졌는가"를 답할 수 없음 |
| 직접/간접 미구분 | `entityLineage.json` 스키마 | `WHERE`/`JOIN` 영향 컬럼을 표현할 수단 없음 |
| CTE 중간 단계 평탄화 | `parser.py` `column_lineage` (4.2) | 다단 변환의 중간 지점 소실 |
| 임시 테이블 경유 시 컬럼 계보 없음 | `sql_lineage.py:1061` | 다홉 컬럼 추적 단절 |
| 프로시저 본문 정적 분석 없음 | 5개 커넥터의 실행 로그 상관 | 미실행 코드 누락, 시간창 오귀속 |
| 필터링된 매핑이 무음 | `validateLineageDetails` | 무엇이 왜 빠졌는지 알 수 없음 |
| 병합이 단조 증가 | `_merge_column_lineage` | 낡은 매핑 잔존 |
| 컬럼 필터가 후처리 | `ColumnFilterMatcher` | 대형 그래프에서 비용이 노드 수에 비례 |

## 10. 본 프로젝트(pl-sql-lineage) 관점의 시사점

### 차용할 만한 것

1. **컬럼 계보를 엣지 속성으로 두는 모델.** 본 저장소의 현재 JSON 계약은 `relationships`를
   평면 배열로 두고 컬럼 객체를 노드로 승격합니다. 그래프 렌더링에는 유리하지만, 테이블 엣지와
   컬럼 엣지의 정합성(끊어진 엣지 검증)을 매번 따로 봐야 합니다. OpenMetadata식 중첩 모델은
   그 정합성이 구조적으로 보장됩니다. 둘 중 어느 쪽이든 **하나를 정본으로 삼고 다른 쪽은
   파생 뷰로 두는 것**이 유지보수에 유리합니다.
2. **FQN 문자열 식별자 + 리네임 추종 코드.** ID 대신 FQN을 쓰면 스키마 변경 때 재작성 비용이
   생기지만(`updateColumnLineage`), 파일 기반 분석에서는 오히려 안정적입니다. 본 저장소도
   `SchemaCatalog`의 ID 일관성 검증에 이 관점을 추가할 여지가 있습니다.
3. **"계보가 있는 컬럼만 보기" 필터와 노드 내 컬럼 검색.** 컬럼 수백 개 테이블에서 그래프가
   무너지는 문제는 실무에서 곧바로 부딪힙니다. `web/index.html`에 저비용으로 이식 가능합니다.
4. **파싱 실패의 격리와 타임아웃.** 30초 타임아웃 + 예외 포획 + 실패 쿼리 목록 누적
   (`QueryParsingFailures`) 패턴은 30만 라인 코퍼스를 돌리는 본 프로젝트에도 그대로 유효합니다.
5. **검색 기반 계층 확장.** 코퍼스가 커져 15홉 체인을 인터랙티브하게 탐색해야 할 때,
   전체 그래프를 한 번에 로드하는 대신 깊이 단위 확장 + `preservePaths` 보정 패턴이 참고가 됩니다.

### 이미 앞서 있거나, 차별화 가능한 지점

1. **변환식 보존.** 본 저장소는 표현식을 관계에 남깁니다. OpenMetadata는 SQL 경로에서 이를
   버립니다. 영향 분석에서 "이 컬럼이 어떻게 계산되는가"는 실무 질문이므로 유지할 가치가 큽니다.
2. **직접/간접 구분.** `WHERE`, `JOIN`, `GROUP BY`, `MERGE ON`, `UPDATE WHERE`의 간접 영향을
   별도 유형으로 남기는 것은 OpenMetadata 스키마에 아예 없는 축입니다.
3. **PL/SQL 본문 정적 분석.** OpenMetadata가 스스로 "구현 가능하지만 미구현"으로 분류한 영역입니다.
   실행 로그에 의존하지 않으므로 미실행 코드와 배포 전 영향 분석을 다룰 수 있습니다.
   이것이 본 프로젝트의 가장 큰 구조적 차별점입니다.
4. **진단(diagnostics) 계약.** OpenMetadata는 해소 실패를 `LOG.debug`로 흘려버립니다.
   본 저장소가 미해결 동적 SQL과 미지원 DML을 진단으로 노출하는 설계는
   "신뢰 경계를 숨기지 않는다"는 점에서 우위입니다.
5. **정답셋 기반 정량 평가.** OpenMetadata는 파서별 단언 on/off로 회귀만 막고 있고,
   컬럼 계보 정확도를 수치로 관리하지 않습니다. 본 저장소의 F1 70.7% / 다홉 완주율 23.6%
   같은 지표는 그 자체로 비교 우위이며, 개선을 측정 가능하게 만듭니다.

### 주의해서 피할 것

- **첫 성공 파서 채택.** 여러 추출 경로를 두게 된다면 "예외 없이 끝났는가"가 아니라
  결과의 품질(엣지 수, 해소율, 진단 수)로 선택해야 합니다. OpenMetadata의 이 정책은
  8절의 40% 불일치와 직접 연결됩니다.
- **중간 단계 평탄화.** CTE 중간 컬럼을 버리면 되살릴 수 없습니다. 축약은 표현 계층에서 하고
  중간 표현에는 전체 경로를 남기는 편이 낫습니다.
- **단조 증가 병합.** 재분석 시 낡은 엣지를 걷어내는 경로를 처음부터 설계해야 합니다.
- **무음 폐기.** 해소되지 않은 매핑은 버리더라도 진단으로 남겨야 커버리지 회귀를 감지할 수 있습니다.

## 부록 — 주요 파일 색인

| 계층 | 경로 |
|---|---|
| 스키마 | `openmetadata-spec/src/main/resources/json/schema/type/entityLineage.json` |
| 스키마 | `openmetadata-spec/src/main/resources/json/schema/type/basic.json` (FQN/sqlQuery/sqlFunction) |
| 스키마 | `openmetadata-spec/src/main/resources/json/schema/configuration/lineageSettings.json` |
| 스키마 | `openmetadata-spec/src/main/resources/json/schema/metadataIngestion/parserconfig/queryParserConfig.json` |
| 스키마 | `openmetadata-spec/src/main/resources/json/schema/api/lineage/searchLineageRequest.json` |
| 스키마 | `openmetadata-spec/src/main/resources/json/schema/api/lineage/esLineageData.json` |
| 색인 매핑 | `openmetadata-spec/src/main/resources/elasticsearch/en/table_index_mapping.json` |
| 파서 | `ingestion/src/metadata/ingestion/lineage/parser.py` |
| FQN 해소 | `ingestion/src/metadata/ingestion/lineage/sql_lineage.py` |
| dialect 매핑 | `ingestion/src/metadata/ingestion/lineage/models.py` |
| 프로시저 계보 | `ingestion/src/metadata/ingestion/source/database/stored_procedures_mixin.py`, `lineage_processors.py` |
| Oracle | `ingestion/src/metadata/ingestion/source/database/oracle/{lineage.py,queries.py}` |
| 클라이언트 병합 | `ingestion/src/metadata/ingestion/ometa/mixins/lineage_mixin.py` |
| 저장/검증 | `openmetadata-service/src/main/java/org/openmetadata/service/jdbi3/LineageRepository.java` |
| 컬럼 필터 | `openmetadata-service/src/main/java/org/openmetadata/service/search/ColumnFilterMatcher.java` |
| 경로 보존 | `openmetadata-service/src/main/java/org/openmetadata/service/search/LineagePathPreserver.java` |
| API | `openmetadata-service/src/main/java/org/openmetadata/service/resources/lineage/LineageResource.java` |
| UI 엣지 | `openmetadata-ui/src/main/resources/ui/src/utils/EntityLineageEdgeUtils.ts` |
| UI 상태 | `openmetadata-ui/src/main/resources/ui/src/context/LineageProvider/LineageProvider.tsx` |
| 테스트 | `ingestion/tests/unit/lineage/queries/test_complex_query_patterns.py` |
| 자체 감사 기준 | `skills/connector-audit/prompts/04-lineage.md` |
