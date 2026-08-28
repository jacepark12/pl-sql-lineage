# 컬럼 계보 저장 스키마 설계

목적: 컬럼 레벨 리니지를 **영속적으로 보관하는** 스키마를 정의합니다.

이 문서는 설계안이며 아직 구현되어 있지 않습니다. 저장소에는 현재 저장 계층이 없습니다.
판단 근거는 [column-lineage-for-agents.md](column-lineage-for-agents.md)의 4절과
[openmetadata-column-lineage.md](openmetadata-column-lineage.md)의 5절(저장 계층)에 있고,
이 문서는 그 결론을 실제 스키마로 옮긴 것입니다.
에이전트에게 **무엇을 저장하는가**가 아니라 **질의당 무엇을 보여주는가**는
[graphify-agent-context.md](graphify-agent-context.md)(패턴)와
[agent-lineage-context.md](agent-lineage-context.md)(이 저장소의 조회 계약)입니다.

## 0. 무엇을 저장하는가

판별 기준은 하나입니다 — **재생성 가능한가.**

| 대상 | 재생성 방법 | 판정 |
|---|---|---|
| 파싱이 뽑은 엣지 | 같은 소스에 엔진 재실행 | 캐시 |
| 그래프 표시용 페이로드 | 저장 계층에서 투영 | 캐시 |
| `lineage_truth.json` | seed 하나로 재생성 (`validate` 가 재현성을 검사) | 테스트 픽스처 |
| 사람의 승인·수정 | **불가능** | 영속 |
| 어느 엔진 버전이 무슨 방법으로 냈는가 | **불가능** (재실행하면 소실) | 영속 |
| 런타임 로그로 해소한 동적 SQL | **불가능** (로그는 rotate 된다) | 영속 |
| T 시점의 리니지 | **불가능** | 영속 |

"(소스 코드, 엔진 버전)의 결정적 함수"인 것은 저장이 아니라 캐시입니다. 아래 스키마는
그 함수로 만들 수 **없는** 것만 담습니다.

## 1. `column_lineage_assertion` — 리니지 본체

```sql
CREATE TYPE lineage_kind AS ENUM (
  -- 값이 흐르는 종류
  'DIRECT','TRANSFORM','AGGREGATE','ANALYTIC','VIA_VARIABLE','VIA_CTE','VIA_PIPELINE',
  -- 값이 흐르지 않는 종류
  'FILTER','CONSTANT','SEVERED','UNRESOLVED'
);
CREATE TYPE lineage_method AS ENUM ('static-parse','runtime-log','native','agent','human');
CREATE TYPE lineage_status AS ENUM ('proposed','accepted','rejected');

CREATE TABLE column_lineage_assertion (
  id            CHAR(32)       PRIMARY KEY,
  to_column     BIGINT         NOT NULL REFERENCES column_ref(id),
  from_columns  BIGINT[]       NOT NULL,
  kind          lineage_kind   NOT NULL,
  expression    TEXT,
  evidence_id   CHAR(32)       REFERENCES evidence(id),
  span          JSONB,
  method        lineage_method NOT NULL,
  confidence    REAL,
  status        lineage_status NOT NULL DEFAULT 'proposed',
  asserted_by   JSONB          NOT NULL,
  supersedes    CHAR(32)       REFERENCES column_lineage_assertion(id),
  valid_from    TIMESTAMPTZ    NOT NULL DEFAULT now(),
  valid_to      TIMESTAMPTZ
);

CREATE INDEX ON column_lineage_assertion (to_column)   WHERE valid_to IS NULL;
CREATE INDEX ON column_lineage_assertion USING GIN (from_columns);
CREATE INDEX ON column_lineage_assertion (evidence_id);
```

이 절부터 4절까지의 DDL 은 설명 순서대로 배치되어 있어 그대로 이어 붙이면 실행되지 않습니다
(`column_ref` 와 `evidence` 가 뒤에 나옵니다). 실행 가능한 순서의 전체 스크립트는
8절에 있습니다.

### id — 내용 주소화

```
id = md5(to_column ‖ sort(from_columns) ‖ kind ‖ expression ‖ method)
```

같은 소스를 다시 분석하면 같은 id가 나옵니다. 재인제스천이 중복을 만들지 않고, 키가 있으니
엣지 **하나만** 수정하거나 철회할 수 있습니다.

키가 없는 스키마는 증분 저장이 원리적으로 불가능합니다. 전체 교체밖에 방법이 없고, 그러면
그 안에 섞여 있던 사람의 수정이 함께 사라집니다. OpenMetadata가 컬럼 매핑 전체를
`entity_relationship` 한 행의 JSON 컬럼에 넣고(`LineageRepository.java:271`)
`addLineage` 가 JSON을 통째로 교체하는 것이 이 실패의 실물입니다.

### 필드별 존재 이유

| 필드 | 없으면 생기는 일 |
|---|---|
| `from_columns` 를 배열로 | 소스별로 행을 쪼개면 "이 컬럼은 두 값의 조합"이라는 사실이 사라진다 |
| `expression` | 함수명만 남기면 `SUM(NVL(x,0))` 과 `SUM(x)` 를 구분하지 못한다 |
| `kind` 에 `UNRESOLVED` / `SEVERED` | "의존성 없음"과 "해소하지 못한 의존성 있음"이 섞인다. Recall 이 의미를 잃고, 에이전트는 답을 보류하는 대신 자신 있게 과소 보고한다 |
| `method` + `asserted_by` | 사람이 고친 엣지를 다음 배치가 덮어쓴다 |
| `confidence` | 정적 파싱의 추정과 런타임 로그의 관측을 같은 무게로 취급하게 된다 |
| `status` | 검토되지 않은 기계 추정이 운영 데이터에 바로 섞인다 |
| `supersedes` | 철회 경로가 없다. 리팩터링으로 사라진 매핑이 영구히 남는다 |
| `span` | 쿼리 전체를 가리킬 뿐 정확한 조각을 인용하지 못한다 |
| `valid_to` | "지난달에는 이 리포트의 리니지가 무엇이었나"에 답할 수 없다 |

`from_columns` 는 빈 배열을 허용합니다. `UNRESOLVED`, `SEVERED`, `CONSTANT` 가 그 경우이며,
소스가 없다는 사실 자체가 기록해야 할 정보입니다.

### 갱신 의미

- 같은 id 가 다시 들어오면 **no-op** 입니다(`INSERT ... ON CONFLICT (id) DO NOTHING`).
  단조 증가 문제가 생기지 않습니다. 이 절의 성질은 쓰는 쪽이 `ON CONFLICT` 를 쓸 때만
  성립합니다. 빼면 재인제스천이 PK 충돌로 실패합니다.
- 내용이 달라지면 새 id 가 만들어지고, 이전 행에 `valid_to` 를 찍은 뒤 새 행이
  `supersedes` 로 그것을 가리킵니다. 삭제하지 않습니다.
- `status='rejected'` 는 삭제가 아닙니다. 다음 배치가 같은 엣지를 다시 제안했을 때
  "이미 기각된 것"임을 알 수 있어야 하기 때문입니다.

## 2. `column_ref` — 컬럼 식별자

```sql
CREATE TABLE column_ref (
  id       BIGSERIAL    PRIMARY KEY,
  schema_  VARCHAR(128) NOT NULL,
  table_   VARCHAR(128) NOT NULL,
  column_  VARCHAR(128),
  UNIQUE (schema_, table_, column_)
);
```

리니지가 컬럼을 **FQN 문자열이 아니라 id로** 참조하는 것이 요점입니다.

OpenMetadata는 컬럼 계보 안에 FQN 문자열을 그대로 박아둡니다. 그 결과 컬럼이 rename 되거나
삭제될 때마다 해당 테이블이 걸린 UPSTREAM 관계 행을 전부 읽어 JSON 안의 FQN을 재작성하는
코드(`LineageRepository.java:1766`)를 유지해야 합니다. id 참조라면 rename 은
`column_ref` 한 행의 UPDATE 로 끝나고 리니지는 건드릴 필요가 없습니다.

`column_` 이 NULL 인 행은 "컬럼이 아니라 테이블 전체가 대상"을 뜻합니다. `WHERE` 절 필터와
미해소 동적 SQL이 여기 해당합니다.

**미결 사항 — 원격 객체.** 코퍼스에는 `SYNWMS.STK_TRX@ERPLINK` 같은 DB 링크 참조가 있습니다
(`score.py:node_key` 는 채점 시 `@` 뒤를 잘라 버립니다). 저장 계층에서는 잘라내면 안 됩니다.
서로 다른 DB 의 동명 테이블이 한 행으로 합쳐지기 때문입니다. `db_link` 컬럼을 추가해
UNIQUE 제약에 포함시키는 편이 낫습니다. 동의어(synonym) 해소도 같은 자리에서 결정해야
합니다.

## 3. `evidence` — 근거 본문

```sql
CREATE TABLE evidence (
  id          CHAR(32)    PRIMARY KEY,
  source_rev  VARCHAR(64) NOT NULL,
  path        TEXT        NOT NULL,
  container   JSONB,
  body        TEXT        NOT NULL
);
```

`id = md5(source_rev ‖ path ‖ body)` 입니다.

- `source_rev` 없이는 `span` 이 썩습니다. 코드가 바뀐 뒤 줄 번호가 엉뚱한 곳을 가리킵니다.
- 한 프로시저에서 엣지 40개가 나와도 본문은 한 번만 저장되고 assertion 들이 참조합니다.
- `container` 가 JSONB 인 이유는 계층마다 위치 정보의 모양이 다르기 때문입니다.
  PL/SQL 은 `{package, procedure}`, EAI 는 `{interface, artifact, step_path, adapter}` 입니다.
  합성 코퍼스의 `location` 필드가 이미 이 두 모양으로 갈라져 있습니다.

## 4. 조회 — 엣지 뷰

매핑 단위 주소화의 대가는 엣지 뷰 재구성에 조인이 필요하다는 것입니다. 그래프 UI 는 진짜로
1:1 엣지를 원하므로 여기서 펴 줍니다.

```sql
CREATE VIEW column_lineage_edge AS
SELECT a.id, a.kind, a.expression, a.confidence,
       s.schema_||'.'||s.table_||'.'||coalesce(s.column_,'*') AS from_fqn,
       t.schema_||'.'||t.table_||'.'||coalesce(t.column_,'*') AS to_fqn
FROM   column_lineage_assertion a
CROSS JOIN LATERAL unnest(a.from_columns) AS src(cid)
JOIN   column_ref s ON s.id = src.cid
JOIN   column_ref t ON t.id = a.to_column
WHERE  a.valid_to IS NULL
  AND  a.status = 'accepted';
```

규모가 커지면 materialized view 로 바꾸거나 검색 엔진에 비정규화합니다. OpenMetadata 가
컬럼 계보 전용 테이블 없이 JSON 한 덩어리로 저장한 탓에 검색 엔진 비정규화가 **필수**가 된
것과 달리, 여기서는 선택입니다.

`web/index.html` 이 읽는 `objects` / `relationships` 계약은 이 뷰의 직렬화 형태입니다.
뷰어 계약은 폐기되는 것이 아니라 이 스키마의 투영으로 남습니다.

## 5. 계층 정리

```
표시   objects / relationships          현 뷰어 계약. 아래 뷰의 직렬화
  ↑ 직렬화
조회   column_lineage_edge (뷰)          파생. 언제든 재생성
  ↑ 투영
저장   column_lineage_assertion          ← 영속 대상은 여기뿐
       + column_ref + evidence
  ↑ 승격 (promote)
파생   엔진이 뽑은 엣지                   캐시. 키 = (source_rev, engine_version)
```

별개로 `lineage_truth.json` 이 있습니다. 엔진 채점용 정답셋이며 이 계층 어디에도 속하지
않습니다. 이 스키마와 닮은 것은 같은 대상을 기술하기 때문이지만, 정답셋에는
`id` / `status` / `method` / `supersedes` / `valid_to` 가 없습니다. **채점용 스냅샷에는
시간도 저자도 필요 없기 때문**이고, 그래서 그것을 그대로 저장 스키마로 쓰면 안 됩니다.

## 6. 합성 코퍼스에서 가져온 것과 버린 것

가져온 것:

- **fan-in 을 한 행에** — `Edge.sources` 가 리스트인 것과 같은 이유입니다.
- **`expression` 에 변환식 전문** — OpenMetadata 는 병합 과정에서 `function` 필드를
  잃습니다(`_merge_column_lineage` 가 `(fromColumns, toColumn)` 튜플만 집합에 넣습니다).
- **해소 실패를 1급 시민으로** — 정답셋의 `UNRESOLVED` / `SEVERED` 를 `kind` 로 승계합니다.
  진단 사이드 채널이 아니라 계보 모델 안에 둡니다.
- **값 흐름 여부의 이분법** — `lineage_kind` 의 두 그룹은 `core.py` 의
  `VALUE_KINDS` / `NON_VALUE_KINDS` 와 같은 경계입니다.

버린 것:

- **식별자 부재** — 정답셋 엣지에는 키가 없습니다. 저장 계층에서는 치명적입니다.
- **줄 단위 위치** — `location.line` 대신 `span`(시작·끝 줄과 열)이 필요합니다.
- **`hops` / `via`** — 전이 거리는 저장할 값이 아니라 그래프 순회로 얻는 값입니다.
  정답셋은 채점 편의를 위해 미리 접어 두었을 뿐입니다.

## 7. 인정하는 비용

- 매핑 단위 주소화는 엣지 뷰 재구성에 조인을 요구합니다. 4절의 뷰로 감당하되, 규모가 커지면
  비정규화가 필요합니다.
- `expression` 이 자유 텍스트이므로 표시와 근거로는 충분하지만 질의는 불가능합니다.
  "COALESCE 로 계산되는 컬럼 전부" 같은 질문이 필요해지면 정규화된 함수 목록을 병기해야 합니다.
- 이력 보존은 테이블을 단조 증가시킵니다. `valid_to IS NOT NULL` 행의 보존 기간 정책이
  별도로 필요합니다.

셋 다 핵심 결정(매핑에 키를 준다)을 미룰 이유는 되지 않습니다.

## 8. 마이그레이션

의존 순서대로 정리한 전체 스크립트입니다. PostgreSQL 16 에서 실행을 확인했습니다.

```sql
BEGIN;

CREATE TYPE lineage_kind AS ENUM (
  'DIRECT','TRANSFORM','AGGREGATE','ANALYTIC','VIA_VARIABLE','VIA_CTE','VIA_PIPELINE',
  'FILTER','CONSTANT','SEVERED','UNRESOLVED'
);
CREATE TYPE lineage_method AS ENUM ('static-parse','runtime-log','native','agent','human');
CREATE TYPE lineage_status AS ENUM ('proposed','accepted','rejected');

CREATE TABLE column_ref (
  id       BIGSERIAL    PRIMARY KEY,
  schema_  VARCHAR(128) NOT NULL,
  table_   VARCHAR(128) NOT NULL,
  column_  VARCHAR(128),
  UNIQUE (schema_, table_, column_)
);

CREATE TABLE evidence (
  id          CHAR(32)    PRIMARY KEY,
  source_rev  VARCHAR(64) NOT NULL,
  path        TEXT        NOT NULL,
  container   JSONB,
  body        TEXT        NOT NULL
);

CREATE TABLE column_lineage_assertion (
  id            CHAR(32)       PRIMARY KEY,
  to_column     BIGINT         NOT NULL REFERENCES column_ref(id),
  from_columns  BIGINT[]       NOT NULL,
  kind          lineage_kind   NOT NULL,
  expression    TEXT,
  evidence_id   CHAR(32)       REFERENCES evidence(id),
  span          JSONB,
  method        lineage_method NOT NULL,
  confidence    REAL,
  status        lineage_status NOT NULL DEFAULT 'proposed',
  asserted_by   JSONB          NOT NULL,
  supersedes    CHAR(32)       REFERENCES column_lineage_assertion(id),
  valid_from    TIMESTAMPTZ    NOT NULL DEFAULT now(),
  valid_to      TIMESTAMPTZ
);

CREATE INDEX ON column_lineage_assertion (to_column)   WHERE valid_to IS NULL;
CREATE INDEX ON column_lineage_assertion USING GIN (from_columns);
CREATE INDEX ON column_lineage_assertion (evidence_id);

CREATE VIEW column_lineage_edge AS
SELECT a.id, a.kind, a.expression, a.confidence,
       s.schema_||'.'||s.table_||'.'||coalesce(s.column_,'*') AS from_fqn,
       t.schema_||'.'||t.table_||'.'||coalesce(t.column_,'*') AS to_fqn
FROM   column_lineage_assertion a
CROSS JOIN LATERAL unnest(a.from_columns) AS src(cid)
JOIN   column_ref s ON s.id = src.cid
JOIN   column_ref t ON t.id = a.to_column
WHERE  a.valid_to IS NULL
  AND  a.status = 'accepted';

COMMIT;
```

`column_lineage_edge` 는 `unnest` 로 fan-in 을 펴므로 `from_columns` 가 빈 배열인 행
(`UNRESOLVED`, `SEVERED`, `CONSTANT`)은 이 뷰에 나타나지 않습니다. 소스가 없는 대상을
화면에 표시해야 한다면 별도 뷰가 필요합니다. 해소 실패를 계보 모델 안에 두기로 한 결정이
조회 계층에서 되살아나는 지점이므로, 뷰를 하나만 만들고 끝내면 안 됩니다.

### 확인 방법

합성 코퍼스의 실제 엣지를 넣어 스키마를 확인할 수 있습니다.

```sh
cd plsql-lineage-corpus && python3 -m synplsql.generate --out out
# out/lineage_truth.json 의 edges 를 column_ref / evidence / column_lineage_assertion 으로 적재
```

`kind` 는 정답셋의 `INDIRECT_FILTER` 를 `FILTER` 로 바꾸는 것 외에 그대로 대응됩니다.
적재 후 `column_lineage_edge` 를 조회하면 `FILTER` 엣지의 `to_fqn` 이
`SYNWMS.MST_VENDOR.*` 처럼 테이블 단위로 나오는 것을 볼 수 있습니다.
