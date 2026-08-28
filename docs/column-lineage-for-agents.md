# AI 에이전트를 위한 컬럼 계보 스키마 설계 검토

분석 대상: [open-metadata/OpenMetadata](https://github.com/open-metadata/openmetadata) `56d99af`
목적: OpenMetadata의 컬럼 계보 스키마를 **AI 에이전트가 소비·생성하는 시스템**의 관점에서 평가하고,
본 저장소가 새 스키마를 설계할 때의 판단 근거를 남깁니다.

스키마 자체의 서술과 다이어그램은 [openmetadata-lineage-schema.html](openmetadata-lineage-schema.html)에,
기능 전반의 분석은 [openmetadata-column-lineage.md](openmetadata-column-lineage.md)에 있습니다.
이 문서는 그 위에서 **설계 판단**만 다룹니다.

## 1. 가장 강한 증거는 OpenMetadata 자신의 에이전트 표면

OpenMetadata는 MCP 서버(`openmetadata-mcp/`)를 이미 출하했습니다. 그 서버가 컬럼 계보를
어떻게 다루는지가 어떤 분석보다 정확한 평가입니다.

### 읽기 — 컬럼 계보가 기본값으로 꺼져 있음

`openmetadata-mcp/src/main/resources/json/data/mcp/tools.json`의 `get_entity_lineage` 정의:

> `includeColumnLineage`: "Defaults to **false** to keep the response table-level and small.
> Set to true only when the user explicitly needs column-to-column lineage, as it
> **can significantly increase response size on wide tables**."

응답은 `McpResponseTrim.MAX_RESPONSE_CHARS = 100_000`으로 하드 절단되고 깊이는 10으로 클램프됩니다.

### 쓰기 — 컬럼 계보를 쓸 수 없고, 시도하면 기존 것이 지워짐

`openmetadata-mcp/.../tools/LineageTool.java`의 쓰기 경로 전체입니다.

```java
AddLineage lineage = new AddLineage()
    .withEdge(new EntitiesEdge().withFromEntity(fromEntity).withToEntity(toEntity));
Entity.getLineageRepository().addLineage(lineage, updatedBy);
```

`LineageDetails`가 없습니다. 그리고 `addLineage`는 details가 없으면 `new LineageDetails()`로
대체한 뒤 upsert 하는데, 그 upsert가 블롭 전체 교체입니다.

```sql
-- CollectionDAO.java:2015
ON DUPLICATE KEY UPDATE json = :json                  -- MySQL
ON CONFLICT (...) DO UPDATE SET json = EXCLUDED.json  -- Postgres
```

즉 **이미 컬럼 매핑이 있는 엣지에 에이전트가 `create_lineage`를 호출하면 그 매핑이 전부 삭제됩니다.**
도구에 `destructiveHint: true`가 붙어 있는 건 정직하지만, 파괴성은 도구의 버그가 아니라
스키마 형태에서 따라 나온 결과입니다.

**요약하면 벤더가 자기 스키마 앞에 에이전트를 세워 보고, 읽기에서는 컬럼 계보를 끄고
쓰기에서는 빼야 했습니다.**

## 2. 역량별 평가

에이전트 연동이 실제로 요구하는 것 대비:

| 요구 | 판정 | 근거 |
|---|---|---|
| 컬럼 하나의 계보를 직접 주소 지정 | ✗ | 컬럼 단위 키가 없음. 엣지를 통째로 받아 배열을 훑어야 함 |
| 응답 크기를 투영/페이징으로 제한 | ✗ | 최소 granularity가 엣지. 컬럼 400개 테이블은 분해 불가능한 블롭 하나 |
| "이 값이 **어떻게** 계산되는가" | ✗ | `function`은 커넥터 1개(SAP HANA)만 채움. 스펙 설명도 *"AVG(), COUNT()"* — 함수 **이름**용 |
| 근거 인용 | ~ | `sqlQuery`는 엣지에 있으나 오프셋 없음. 쿼리 전체는 인용 가능, 해당 조각은 불가 |
| 신뢰도 판단 | ~ | `source` 열거형이 거친 출처만 제공. confidence 없음, 파서 귀속 없음 |
| "모른다"와 "관계 없음"의 구분 | ✗ | 해소 실패 매핑이 두 계층에서 무음 폐기. **부재를 반증할 수 없음** |
| 값 흐름 vs 필터 영향 | ✗ | 필드 자체가 없음. `WHERE`/`JOIN` 컬럼은 아예 미기록 |
| 멱등 쓰기 | ✗ | 매핑에 자연키 없음. 재시도 의미 미정의 |
| 잘못된 주장 철회 | ✗ | 클라이언트 병합이 단조 합집합. `deleteLineageBySource` 일괄 삭제만 존재 |
| 확정 아닌 제안 | ✗ | 리뷰 상태 없음. `suggestion.json`은 `SuggestDescription`/`SuggestTagLabel` 두 종뿐 |
| 에이전트/모델/실행 귀속 | ✗ | `updatedBy`는 사용자명 문자열 |
| 확장 지점 | ✗ | 두 엣지 타입 모두 `additionalProperties: false` |

참고로 `confidence`는 OpenMetadata 스펙의 다른 곳(classification, recognizer)에는 있습니다.
계보로 확장되지 않았을 뿐입니다.

## 3. 가져올 만한 것

경고만 있는 건 아닙니다. 세 가지는 그대로 차용할 가치가 있습니다.

**저장과 색인이 생성 타입을 공유.** `EsLineageData.columns`가 코어의 `columnLineage`를
`$ref` 합니다. 하나의 타입이 쓰기·읽기·색인을 모두 담당하므로 표현 간 드리프트가 원천적으로 불가능합니다.

**증거와 주장의 분리 본능.** `sqlQueryKey`는 반복되는 SQL을 부모 문서의 맵으로 빼내고 키로 참조합니다.
큰 증거를 주장에서 떼어 키로 잇는 이 패턴은 에이전트 페이로드에 정확히 맞는 방향입니다.
버릴 게 아니라 일반화할 패턴입니다.

**비정규화 순회.** 하류 문서마다 상류 엣지를 심어 두어 깊이당 질의 1회로 확장합니다.
에이전트가 "한 홉 더" 를 반복하는 추론 패턴과 잘 맞습니다.

**스키마 변경 추종을 처음부터 계획.** `updateColumnLineage`가 리네임 시 FQN을 재작성하고
삭제 시 매핑을 제거합니다. 문자열 식별을 택하면 반드시 필요해지는 코드이므로,
나중에 발견하는 것보다 처음부터 설계에 넣는 편이 낫습니다.

## 4. 설계 판단 — 하나의 결정이 아홉 개의 결과를 만든다

2절 표의 모든 ✗는 독립된 결함이 아닙니다. **매핑이 주소 지정 가능하지 않다**는
단 하나의 결정에서 파생됩니다.

```
매핑에 키가 없다
  ├─ 대상 지정 읽기 불가        → 응답 크기 제어 불가
  ├─ 부분 쓰기 불가             → 블롭 전체 교체 → 데이터 소실 위험
  ├─ 철회 불가                  → 단조 합집합만 가능
  ├─ 매핑별 주석 위치 없음      → confidence / method / span 둘 데가 없음
  └─ 스키마 확장 불가           → additionalProperties: false
```

따라서 새 스키마에서 의도적으로 결정할 것은 **granularity 하나**입니다.
시작 시점에는 싸고, 나중에 바꾸려면 비쌉니다.

### 제안 형태

```jsonc
ColumnLineageAssertion {
  id,                          // 안정 키. hash(fromColumns[], toColumn, method) 등 내용 주소화
  fromColumns[], toColumn,
  kind: "direct" | "filter" | "join" | "group" | "order",
  expression: string,          // 함수 이름이 아니라 실제 변환식
  evidenceRef: id,             // → SQL/파일 본문. 한 번만 저장하고 참조
  span: { file, startLine, startCol, endLine, endCol },
  method: "static-parse" | "runtime-log" | "native" | "agent" | "human",
  confidence: 0.0–1.0,
  status: "proposed" | "accepted" | "rejected",
  assertedBy: { kind, id, model?, runId? },
  supersedes: id?
}
```

에이전트 관점에서 특히 무거운 셋:

- **`span`** — 쿼리 전체가 아니라 정확한 조각을 인용하게 합니다. 인용과 손짓의 차이입니다.
- **`status`** — 에이전트가 쓸 수 있게 되는 순간 필요합니다. 검토 전까지 운영 데이터에 섞이지 않습니다.
- **`supersedes`** — 철회 경로. 합집합 병합 모델로는 절대 표현할 수 없습니다.

### 해소 실패를 1급 시민으로

본 저장소는 이미 미해결 동적 SQL을 진단으로 냅니다. 이걸 **계보 모델 안으로** 가져와야 합니다
(사이드 채널이 아니라). "의존성 없음"과 "해소하지 못한 의존성 있음"을 구분할 수 있는 에이전트는
자신 있게 과소 보고하는 대신 답을 보류합니다. 무음 폐기는 OpenMetadata 스키마가
이 용도에서 가진 가장 비싼 성질입니다.

### 비용 인정

- 매핑 단위 주소화는 엣지 뷰 재구성에 조인을 요구합니다. 그래프 UI는 진짜로 엣지를 원하므로
  엣지 형태의 투영을 따로 비정규화해 두는 편이 낫습니다.
- `expression`을 자유 텍스트로 두면 표시와 근거로는 충분하지만 질의는 불가능합니다.
  "COALESCE로 계산되는 컬럼 전부" 같은 질문이 나중에 필요하면 정규화된 함수 목록을 병기해야 합니다.

둘 다 핵심 결정을 미룰 이유는 되지 않습니다.

## 5. 피할 것

- **첫 성공 파서 채택.** 추출 경로가 여럿이면 "예외 없이 끝났는가"가 아니라 결과 품질로 골라야 합니다.
- **중간 단계 평탄화.** CTE 중간 컬럼은 버리면 복원 불가입니다. 축약은 표현 계층에서.
- **단조 증가 병합.** 재분석 시 낡은 엣지를 걷어내는 경로를 처음부터.
- **무음 폐기.** 버리더라도 진단으로 남겨야 커버리지 회귀를 감지할 수 있습니다.
- **닫힌 스키마.** `additionalProperties: false`를 기본으로 두면 나중에 신뢰도·귀속을
  붙일 자리가 없습니다.

## 6. 검색·주입 계층은 별도 계약이다

이 문서의 ✗는 **저장 granularity**에서 나옵니다. 주소 가능한 assertion을 만들어도
에이전트 프롬프트에 그래프 전체를 넣으면 같은 크기 문제에 다시 부딪힙니다.

코드 심볼 그래프에서 그 다음 계층 — 디스크에 진실을 두고, 질의당 예산을 가진
텍스트 부분 그래프만 주고, always-on 규칙으로 grep보다 query를 강제하는 방식 — 은
[Graphify](https://github.com/Graphify-Labs/graphify)가 이미 구현해 있습니다.
코드 근거와 본 스키마에의 함의는 [graphify-agent-context.md](graphify-agent-context.md)에 있습니다.

이 저장소의 읽기 계약은 [agent-lineage-context.md](agent-lineage-context.md)입니다.
`plsqllineage.query` 가 FQN으로 상류 부분 그래프를 예산 있는 텍스트로 자릅니다.
