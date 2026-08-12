# 합성 EAI(webMethods) 코퍼스 생성기 기획서

**문서 목적** — 컬럼 레벨 리니지 엔진이 **시스템 간 연계 구간**까지 추적할 수 있도록,
webMethods Integration Server 기반 EAI 아티팩트의 합성 코퍼스 생성기를 설계한다.

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-08-12 |
| 선행 문서 | [`PLAN.md`](PLAN.md) — 합성 PL/SQL 코퍼스 생성기 기획서 |
| 대상 플랫폼 | webMethods Integration Server (Software AG) |
| 분석 표본 | 인터페이스 2건 (구조·통계만 인용, 코드 미이식) |
| 산출물 | 합성 EAI 패키지 + 리니지 정답셋 (PL/SQL 코퍼스와 접합) |

구현 상태는 [../README.md](../README.md), 바이너리 포맷의 근거와 한계는
[WM-VALUES-FORMAT.md](WM-VALUES-FORMAT.md)에 있다. 기획과 달라진 부분은 11장에 정리했다.

---

## 1. 배경 — EAI가 리니지의 단절 구간이다

PL/SQL 코퍼스만으로는 **DB 하나 안에서의 리니지**밖에 못 잇는다. 실제 질문은 대개
시스템 경계를 넘는다.

> "이 리포트의 화주명은 원래 어느 시스템의 어느 컬럼에서 왔는가?"

이 질문의 답은 PL/SQL에 없다. 원천은 다른 DB에 있고, EAI가 그 사이를 잇는다.
EAI 구간을 해석하지 못하면 리니지 그래프는 인터페이스 테이블에서 끊긴 채로 남는다.

### 1.1 표본에서 확인된 실제 연결

분석 표본의 EAI 인터페이스는 원천 DB에서 읽어 인터페이스 스키마의 테이블에 적재하고,
앞서 분석한 PL/SQL 자산에는 그 테이블을 소비하는 패키지가 실재한다. 즉 **EAI 코퍼스와
PL/SQL 코퍼스는 인터페이스 테이블에서 접합**된다. 두 생성기가 동일한 가상 스키마를
공유하면 전 구간 리니지 체인이 완성된다. 이것이 EAI 코퍼스를 별도로 만드는 것이 아니라
PL/SQL 코퍼스의 **확장**으로 설계해야 하는 이유다.

### 1.2 합성이 필요한 이유는 PL/SQL과 동일

운영 EAI 패키지 역시 반출 불가 자산이며, 오히려 PL/SQL보다 민감하다 —
접속 정보(`connectionName`), 스키마명, 시스템 간 연계 구조가 그대로 드러난다.
표본에서는 DB 암호화 함수 호출까지 노출된다.

---

## 2. 대상 플랫폼 구조 분석 (실측)

### 2.1 패키지 디렉터리 구조

```
<인터페이스>/
├── node.idf                         인터페이스 노드 정의 (네임스페이스)
├── adpt/<svc>/node.ndf              JDBC 어댑터 서비스 (Select / Insert / Update)
├── docs/<doc>/node.ndf              IS 문서 타입 (메시지 스키마)
└── srvc/<svc>/flow.xml              FLOW 서비스 (source / start / target)
```

### 2.2 리니지 경로 모델 (5홉)

```
[원천 DB]  원천테이블.컬럼
    │  ① Select 어댑터  (select.outputField ↔ tables.columnInfo)
    ▼
[문서]     docs:<원천문서> / results / <필드>
    │  ② source flow → start flow (파이프라인 전달)
    ▼
[FLOW]     <MAPCOPY FROM=".../results/<필드>" TO=".../<타깃문서>/<컬럼>">
    │  ③ target flow 필드 매핑  (+ MAPINVOKE 변환기 경유 가능)
    ▼
[문서]     docs:<타깃문서> / <컬럼>
    │  ④ Insert 어댑터  (update.inputField → update.column)
    │     update.expression = <암호화함수>(?)  ← DB측 변환 개입
    ▼
[타깃 DB]  인터페이스스키마.테이블.컬럼
    │  ⑤ 이후 PL/SQL 패키지가 소비 → PLAN.md 코퍼스로 연결
    ▼
```

**핵심 성질** — ③의 `MAPCOPY`는 **명시적 필드 대 필드 매핑**이다. PL/SQL처럼
SQL을 해석해 유추할 필요가 없다. 즉 **EAI 구간은 PL/SQL보다 리니지 정확도를
높게 뽑을 수 있다.** 대신 난점이 다른 곳에 있다(3장).

### 2.3 FLOW 구문 실측 분포

인터페이스 2건 / FLOW 서비스 6개 기준.

| 구문 | 개수 | 리니지 의미 |
|---|---:|---|
| `MAPCOPY` | 199 | **직접 필드 매핑 = 리니지 엣지 그 자체** |
| `MAP` | 160 | 매핑 스텝 컨테이너 |
| `MAPDELETE` | 96 | 파이프라인 필드 제거 — 리니지 **단절** 지점 |
| `INVOKE` | 60 | 서비스 호출 (어댑터/공통/트랜잭션) |
| `MAPSET` | 42 | 리터럴 상수 대입 — 원천 없는 엣지 |
| `SEQUENCE` | 38 | 블록 (try/catch 포함) |
| `MAPINVOKE` | 16 | **인라인 변환기 = TRANSFORM 엣지** |
| `BRANCH` | 4 | 조건 분기 — 조건부 리니지 |
| `LOOP` | 2 | 배열 반복 — 차원 변화 |

**MAPCOPY 경로 깊이 분포** (`FROM` 속성의 계층 단계 수): 1단 47 / 2단 32 / 3단 114 / 4단 6.

### 2.4 사용된 변환기 (MAPINVOKE / INVOKE)

`pub.math:addInts`(4), `pub.math:roundNumber`(4), `pub.string:replace`(4),
`pub.string:substring`(3), 커스텀 `substringRT`(2), `pub.string:numericFormat`(1),
`pub.string:tokenize`(2 — 1 입력 → 배열, 차원 변화),
`pub.art.transaction:*`(12 — 트랜잭션 경계, 엣지 없음),
`pub.flow:clearPipeline`(8 — **파이프라인 전체 소거 = 대량 단절**).

### 2.5 어댑터 템플릿 4종

| 템플릿 | 표본 | 리니지 해석 |
|---|---:|---|
| `Select` | 2 | `tables.columnInfo` + `select.outputField` → 컬럼→필드 |
| `Insert` | 2 | `update.inputField` → `update.column` → 필드→컬럼 |
| `Update` | 2 | 위와 동일 + WHERE 조건 컬럼 = INDIRECT |
| `CustomSQL` | 1 | **임의 SQL** — SQL 파서 필요 (PL/SQL 엔진 재사용) |

---

## 3. 난점 — PL/SQL과 성격이 다르다

### 난점 1. 어댑터 메타데이터가 base64 바이너리 블롭에 있다 ★

리니지에서 가장 중요한 **DB 테이블·컬럼 바인딩**이 XML 텍스트가 아니라
`IRTNODE_PROPERTY` 값 하나에 base64로 인코딩되어 들어 있다. 디코딩하면 webMethods
`Values` 직렬화 포맷이 나오며, 여기에만 존재하는 정보는 다음과 같다.

`serviceTemplateName`(연산 종류), `connectionName`(**어느 DB인가**),
`tables.realSchemaName`(**어느 스키마인가**), `tables.tableName`(**어느 테이블인가**),
`tables.columnInfo`(컬럼 카탈로그), `update.column`/`update.inputField`(엣지 양끝),
`update.expression`(**TRANSFORM / 상수**), `select.outputField`/`select.refColumn`,
`joins.leftColumn`.

`update.expression`의 DB측 암호화 함수는 특히 중요하다 — 소스 어디에도 SQL 텍스트로
나타나지 않는 변환이 바이너리 안에만 존재한다. 이걸 놓치면 "암호화되어 적재됨"이라는
사실이 리니지에서 통째로 사라진다.

**관측된 포맷** — 태그 1바이트 + 길이 2바이트 + UTF-16LE 페이로드. 상세와 한계는
[WM-VALUES-FORMAT.md](WM-VALUES-FORMAT.md) 참고. 생성기는 이 블롭을 **인코딩**할 수
있어야 하므로 디코더뿐 아니라 인코더 구현이 선행 작업이다.

### 난점 2. MAPCOPY 경로 문법

```
/<문서>;4;0;<문서타입참조>/results;2;0/<필드>;1;0
 └ 필드명 ┘ │ │              └ 필드 ┘ │ │
           │ └ 차원(0=스칼라)         │ └ 차원
           └ 타입코드(1=string, 2=record, 4=recref)
```

세미콜론 구분 메타데이터가 붙은 경로다. 파싱 자체는 쉬우나 **문서 타입 참조를
따라가 실제 필드를 해석**해야 하고, 배열 차원이 섞이면 홉 간 카디널리티가 바뀐다.

### 난점 3. 파이프라인 부작용 — 리니지 단절

webMethods FLOW는 **파이프라인**이라는 전역 변수 공간에서 동작한다.
`MAPDELETE`(96회)는 필드를 제거하고, `pub.flow:clearPipeline`(8회)은 `preserve` 목록
외 전부를 소거하며, `MAPSET`(42회)은 원천 없이 리터럴을 주입한다.

즉 **문장 순서를 무시하고 매핑만 수집하면 틀린 리니지가 나온다.** 파이프라인
상태를 순차 시뮬레이션해야 한다. PL/SQL 변수 추적보다 상태 공간이 크다.

### 난점 4. CustomSQL 어댑터

임의 SQL을 담으므로 결국 SQL 파서가 필요하다. **PL/SQL 엔진을 그대로 재사용**하는
설계가 맞고, 두 코퍼스가 같은 엔진을 공유해야 하는 또 하나의 근거다.

---

## 4. 설계 원칙

[`PLAN.md`](PLAN.md) 2장의 4개 원칙(정답에서 역생성 / 구조적 충실도 / 재현
가능성 / 난이도 계층화)을 그대로 승계한다. EAI 고유 원칙 2개를 추가한다.

### 원칙 5. PL/SQL 코퍼스와 스키마를 공유한다

EAI 생성기는 독립 코퍼스가 아니라 **PL/SQL 코퍼스의 앞단**이다.

```
[가상 원천 DB]         [EAI 합성 패키지]      [가상 타깃 DB]        [PL/SQL 합성 패키지]
SYNSRC.SRC_ITEM_MST ─▶ SYN_WMS_S_0001 ─▶ SYNIF.IF_ITEM_RCV ─▶ PKG_* ─▶ SYNWMS.MST_ITEM
                                                                         │
                                                                         ▼
                                                              … ─▶ RPT_DAILY_STK
```

**결과** — 최장 리니지 체인이 6홉에서 **15홉**으로 늘어난다.
리포트 컬럼에서 역추적해 `SYNSRC` 원천 컬럼까지 도달하는지가 통합 엔진의 최종
검증 항목이 된다.

### 원칙 6. 바이너리 블롭을 회피하지 않는다

`IRTNODE_PROPERTY`를 평문 XML로 대체한 "쉬운 합성 데이터"를 만들면 코퍼스의
의미가 없어진다 — 실전에서 엔진이 마주칠 가장 큰 장벽이 바로 그것이기 때문이다.

이 원칙은 **부분적으로만** 지켜졌다. 관측 표본이 33바이트 1건뿐이라 실제 바이트
호환성을 확보할 수 없었기 때문이다. 무엇이 지켜지고 무엇이 지켜지지 않았는지는
[WM-VALUES-FORMAT.md](WM-VALUES-FORMAT.md) 6장에 명시했다.

---

## 5. 생성 대상 아티팩트 명세

| 아티팩트 | 형식 | 생성 내용 |
|---|---|---|
| `<IF>/node.idf` | XML | 인터페이스 노드, 네임스페이스 |
| `<IF>/adpt/<svc>/node.ndf` | XML + base64 블롭 | 어댑터 시그니처 + `IRTNODE_PROPERTY` |
| `<IF>/docs/<doc>/node.ndf` | XML | 문서 타입 필드 정의 |
| `<IF>/srvc/<svc>/flow.xml` | XML (FLOW 3.0) | MAP/MAPCOPY/MAPINVOKE/BRANCH/LOOP |
| `<IF>/srvc/<svc>/node.ndf` | XML | FLOW 서비스 시그니처 |
| `lineage_truth.json` | JSON | PL/SQL 코퍼스와 **동일 스키마**의 정답 엣지 |

정답 포맷은 `PLAN.md` 5.4를 공유하되, `location`에 EAI 좌표를 추가한다.

```json
{
  "target": { "table": "SYNIF.IF_CUST_RCV", "column": "CUST_NM" },
  "sources": [ { "table": "SYNSRC.SRC_CUST_MST", "column": "CUST_NAME" } ],
  "kind": "TRANSFORM",
  "transform": "select.outputField[CUST_NAME] = CUST_NAME → SYNCRYPT.FN_ENC(?)",
  "hops": 3,
  "via": ["PIPELINE"],
  "location": {
    "layer": "eai",
    "interface": "SYN_WMS_S_0003",
    "artifact": "srvc/SYN_WMS_S_0003_target/flow.xml",
    "step_path": "SEQUENCE[0]/SEQUENCE[0]/INVOKE[1]",
    "adapter": "adpt/IF_CUST_RCV_I_01"
  }
}
```

`step_path`를 넣는 이유 — FLOW는 텍스트 라인 번호보다 **스텝 트리 경로**가
안정적인 좌표다. GUI 도구에서 해당 스텝을 바로 찾아갈 수 있어야 디버깅이 된다.

---

## 6. 난이도 티어

| Tier | 내용 | 비중 | 검증 목표 |
|---|---|---:|---|
| **0** | Select→MAPCOPY 1:1→Insert, 변환기 없음 | 20% | 블롭 디코딩 + 경로 파싱 |
| **1** | 스테이징 경유, 3·4단 중첩 경로, MAPSET 상수, MAPINVOKE 변환기 | 35% | 기본 매핑 정확도 |
| **2** | LOOP 배열, MAPDELETE 단절, Update 어댑터 WHERE | 30% | 파이프라인 상태 추적 |
| **3** | BRANCH 조건부 적재, `clearPipeline`, CustomSQL | 15% | 한계 시험 |

Tier 2의 `MAPDELETE` / Tier 3의 `clearPipeline`이 이 코퍼스의 핵심 감별
항목이다. 이걸 무시하는 엔진은 Tier 0~1에서 만점을 받고 Tier 2에서 무너진다.

---

## 7. 아키텍처

```
plsql-lineage-corpus/
├── docs/
│   ├── PLAN.md
│   ├── PLAN-EAI.md              이 문서
│   └── WM-VALUES-FORMAT.md      바이너리 포맷 명세 (관측/가정 분리)
├── profile-eai.json             FLOW 구문 분포 사양
├── synplsql/                    (PL/SQL 생성기 — SYNSRC 스키마와 엣지 종류를 공유)
├── syneai/
│   ├── wmvalues.py              webMethods Values 바이너리 인/디코더  ★선행
│   ├── nodes.py                 node.idf / FLOW 서비스 node.ndf 생성
│   ├── docs.py                  IS 문서 타입 생성
│   ├── adapters.py              JDBC 어댑터 4종 템플릿 + 블롭 생성
│   ├── flow.py                  FLOW IR + XML 렌더러 + 경로 문법
│   ├── interfaces.py            인터페이스 조립 (문서/어댑터/서비스)
│   ├── pipeline.py              파이프라인 상태 시뮬레이터 (정답 산출)
│   ├── generate.py              CLI + 통합 정답셋 병합
│   └── validate.py              자체 검증 + 픽스처 검사
└── fixtures-eai/                수작업 엣지케이스 9건
```

`synplsql/core.py`의 엣지 분류를 **양쪽이 공유**한다. `PLAN.md` 5.3의 8종에
EAI 전용 3종을 추가했다.

| 추가 엣지 종류 | 발생 | 의미 |
|---|---|---|
| `VIA_PIPELINE` | MAPCOPY 연쇄 | 파이프라인 변수 경유 |
| `CONSTANT` | MAPSET / `update.expression` 리터럴 | 원천 없는 대입 |
| `SEVERED` | MAPDELETE / clearPipeline | 이 지점에서 리니지 종료 |

`SEVERED`를 정답에 명시하는 이유 — "엔진이 못 찾은 것"과 "실제로 끊긴 것"을
구분해야 Recall 지표가 의미를 갖는다.

---

## 8. 작업 계획과 진행 상태

| Phase | 작업 | 상태 |
|---|---|---|
| **E1** | `Values` 바이너리 포맷 리버스 엔지니어링 — 디코더 | 부분 완료 (11장 1번) |
| **E2** | 인코더 + 왕복 검증 | 완료 (표본 대조는 33바이트 접두부만) |
| **E3** | `SYNSRC` 원천 스키마 추가, `SYNIF` 접합 확정 | 완료 |
| **E4** | 문서 타입 + 어댑터 생성기 (Select/Insert/Update) | 완료 |
| **E5** | FLOW 생성기 — Tier 0~1 (MAPCOPY/MAPSET) | 완료 |
| **E6** | 파이프라인 시뮬레이터 + 정답 산출 | 완료 |
| **E7** | Tier 2 — MAPINVOKE 변환기, LOOP, MAPDELETE | 완료 |
| **E8** | Tier 3 — BRANCH, clearPipeline, CustomSQL | 완료 |
| **E9** | PL/SQL 코퍼스와 통합 정답셋 병합 + 다홉 체인 검증 | 완료 (15홉) |

---

## 9. 리스크 및 대응

| 리스크 | 영향 | 실제 결과 |
|---|---|---|
| `Values` 바이너리 포맷 RE 실패 | E2 이후 전면 중단 | **현실화됨.** 표본 33바이트로는 배열/레코드 태그 관측 불가 → 규약 기반 인코딩으로 진행하고 한계를 문서화 (11장 1번) |
| 파이프라인 시뮬레이터가 실제 런타임과 불일치 | 정답 오염 | 시뮬레이터 의미론을 `pipeline.py`에 문서화하고, 수작업 픽스처 9건으로 교차 검증 |
| 합성 FLOW가 실제보다 단순 | 과적합 | MAPCOPY 경로 깊이 분포와 구문 비율을 생성 목표치로 고정, `--stats`로 강제 |
| 표본이 2건뿐이라 통계 신뢰도 부족 | 프로파일 편향 | 실측치를 참고선으로만 사용, 구조적 구문은 서비스당 비율로 분리 모델링 (11장 2번) |
| 실제 접속명·스키마명 유입 | 반출 제약 위반 | 식별자 `SYN*` 강제 + 생성물 전수 블랙리스트 검사 (`no_sampled_identifier`) |

---

## 10. 기대 효과

1. **전 구간 추적** — 원천 DB → EAI → 인터페이스 테이블 → PL/SQL → 리포트, 15홉
2. **단절 구간 식별** — `MAPDELETE` / `clearPipeline` / 동적 SQL을 정직하게 "끊김"으로 보고
3. **숨은 변환 탐지** — 바이너리 블롭 안의 DB측 암호화 함수 개입
4. **플랫폼 간 일관성** — 동일한 엣지 분류 체계로 SQL과 EAI를 같은 그래프에 표현

특히 3번은 실무 가치가 크다. 개인정보 컬럼이 어디서 암호화되는지를 소스 검색으로는
찾을 수 없고, 오직 어댑터 메타데이터를 해석해야만 알 수 있기 때문이다.

---

## 11. 기획 대비 변경 사항

1. **바이너리 포맷은 규약 기반으로 구현했다 (원칙 6의 부분 달성)** — 기획 8장은 E1~E2의
   통과 기준을 "표본 블롭 디코드→인코드→바이트 일치"로 정했으나, 사용 가능한 표본이
   base64 조각 1건(33바이트)뿐이었다. 그 안에는 문자열 태그 하나만 나타나고, 정작
   리니지에 필요한 값(`tables.columnInfo`, `update.column`, `update.expression`)은
   전부 배열이라 인코딩 근거가 없다. 관측된 8바이트 전문과 문자열 태그는 실측대로
   구현하고 — 생성 블롭의 선두 33바이트는 표본과 **정확히 일치**한다 — 나머지 태그는
   규약으로 선언한 뒤 `docs/WM-VALUES-FORMAT.md`에 관측과 가정을 분리해 기록했다.
   태그 표는 `wmvalues.py`의 `TAGS` 한 곳에만 있어, 실제 포맷이 밝혀지면 그 딕셔너리와
   `PREAMBLE`만 교체하면 된다. `--verify <실제블롭>` 명령으로 즉시 대조할 수 있다.
   **실제 webMethods 디코더와의 호환성은 검증되지 않았다.**

2. **구문 프로파일을 두 축으로 분리했다** — 기획은 모든 구문을 인터페이스당 개수로
   봤으나, 표본 인터페이스는 39컬럼 테이블을 다루고 이 코퍼스의 가상 테이블은 더 좁다.
   필드 수에 비례하는 구문(MAP/MAPDELETE/MAPSET/MAPINVOKE)은 MAPCOPY 대비 비율로,
   스텝 블록 단위로 존재하는 구문(INVOKE/SEQUENCE/BRANCH/LOOP)은 서비스당 개수로
   나눠 관리한다. 한 축으로 묶으면 좁은 스키마에서 구조적 구문이 부당하게 줄어든다.

3. **MAPCOPY 경로 깊이를 생성 시점에 정확히 배분한다** — 매핑에서 자연 발생하는 3단
   경로 개수를 기준으로 1·2·4단 하우스키핑 복사본을 필요한 만큼 정확히 생성한다.
   그냥 두면 3단이 거의 전부가 되어 실측 분포(3단 57%)와 어긋난다.

4. **`BRANCH`/`LOOP`를 Tier 3 전용에서 해제했다** — 기획은 BRANCH를 Tier 3에 뒀으나,
   실측 빈도(서비스당 0.67)는 그 비중으로 재현할 수 없다. 리니지를 가르는 조건부
   적재는 Tier 3에 남기고, 로그 경로만 고르는 제어용 BRANCH는 전 티어에 배치했다.
   둘을 구분하는 것 자체가 엔진에 대한 시험이 된다.

5. **`stmt_id` 대신 `step_path`만 사용한다** — 기획 5장의 예시대로 스텝 트리 경로가
   FLOW의 안정적 좌표이며, 별도의 문장 번호는 엔진이 대조할 수 없어 넣지 않았다.

6. **표본에서 관측한 식별자를 코퍼스에서 제거했다** — 초기 구현은 기획 본문에 인용된
   실제 함수명·접속명 표기를 그대로 썼다. 리스크 표의 "실제 접속명·스키마명 유입"에
   해당하므로 전부 `SYN*` 계열로 교체하고, 생성물 전수를 검사하는
   `no_sampled_identifier` 검증을 추가했다.

7. **11장 확인 필요 사항의 처리** — 추가 표본은 확보되지 않아 1번으로 귀결됐다.
   CustomSQL 비중은 Tier 3에 두되 `profile-eai.json`에서 조정 가능하게 했고,
   전체 인터페이스 규모는 기본 40건 + `--interfaces` 플래그로 열어 뒀다.
