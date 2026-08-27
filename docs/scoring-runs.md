# 합성 코퍼스 채점 기록

엔진 로드맵의 현재 요약은 [engine-roadmap.md](engine-roadmap.md)에 있습니다.
이 문서는 **언제, 어떤 명령으로, 어떤 규모를 채점했는지**만 남깁니다.
합성 점수는 "이 구문 분포에서 이 정도"이지 실무 PL/SQL 일반화가 아닙니다
([validation-limits.md](validation-limits.md)).

생성물 `plsql-lineage-corpus/out/` 은 gitignore 입니다. 같은 seed·기본 규모로
재생성하면 바이트 단위로 같은 코퍼스가 나옵니다. `--input` 은 항상 코퍼스
**루트**입니다 (`packages/` 를 넘기면 `location.file` 이 정답셋과 어긋나 티어별
표가 0% 가 됩니다).

## 2026-08-26 — 기본 코퍼스 전체 (JAC-160)

문서상 기본 코퍼스(seed `20260812`)를 **축소 없이** 엔진 + scorer 로 돌린 첫 기록입니다.
베이스는 `origin/cursor/engine-production-gaps-2a0d` (`37947e4`, 동적 SQL 진단 /
ALL_SOURCE 접두 / DB link). 이 브랜치에 파일별 parse vs rest 타이머만 더했습니다
(`37aa552`).

환경: Python 3.12.3, sqlglot 30.17.0, antlr4-python3-runtime 4.13.2, OpenJDK 21,
Linux 6.12, 4 vCPU / 15 GiB RAM / swap 없음. GNU `/usr/bin/time` 은 없어서
`resource.getrusage` 로 벽시계·user/sys·peak RSS 를 쟀습니다.

### 생성

```sh
cd plsql-lineage-corpus
python3 -m synplsql.generate --out out/full --stats
```

기본값(profile `scale.packages=200`, `scale.lines=300000`, seed `20260812`)이
문서의 201 / 300,612 를 만듭니다. `--packages` / `--lines` 는 넣지 않았습니다.

| | 값 |
|---|---:|
| 패키지 | 201 (평균 1,503 / 최대 32,655 라인) |
| 총 라인 | 300,612 |
| 프로시저 / 함수 | 563 / 95 |
| 정답 엣지 | 8,629 (REF CURSOR 투영 182) |
| 엣지 종류 | AGGREGATE 70, ANALYTIC 161, DIRECT 2,890, INDIRECT_FILTER 2,888, TRANSFORM 1,485, UNRESOLVED 126, VIA_CTE 464, VIA_VARIABLE 545 |
| 최장 체인 | 15홉 |

`--stats` 구문 프로파일 24항목 전부 허용오차 안(OK). 생성 자체는 약 3초.

### 엔진

```sh
cd plsql-lineage-engine
python3 scripts/build_parser.py
PYTHONPATH=. python3 -m plsqllineage.engine \
  --input ../plsql-lineage-corpus/out/full \
  --out /tmp/engine-full.json \
  --progress --timings /tmp/engine-full-timings.json
```

`--progress` / `--timings` 는 측정용입니다. 엣지 JSON 계약은 그대로입니다.

| | 값 |
|---|---|
| 파싱 | **201/201** (`PARSE_FAILED` 0, `DECODE_FAILED` 0) |
| 엔진 엣지 (raw) | 7,780 |
| 진단 | 548, 전부 warning |
| 벽시계 | **183.563s** (user 173.679s / sys 9.593s) |
| peak RSS | 469,732 kB (**459 MiB**) |
| 라인/s | **1,638.4** 전체 / 첫 파일 **44.4** / 이후 200파일 **1,737.4** (DFA 웜) |
| parse vs 나머지 | parse 153.13s (**83.5%**) / sqlmap+dataflow 30.31s |

진단 코드:

| code | 건수 | 내용 |
|---|---:|---|
| `UNRESOLVED` | 315 | `SEQ_*.NEXTVAL` (시퀀스), `G_JOB_ID`/`G_STEP_NO`/`V_CNT` (전역·카운터), `REC.*` / `T_ROWS.*` (레코드·컬렉션 필드) |
| `DYNAMIC_SQL` | 126 | 생성기 `EXEC_IMMEDIATE` 126건과 일치. 엣지 없음이 정상 |
| `PARAMETER_UNRESOLVED` | 107 | 주로 `P_WH_CD` (73), `P_STEP_NM` (32) |
| `SQL_NOT_ANALYZED` | 0 | |
| `STAR_UNRESOLVED` | 0 | 카탈로그를 코퍼스 루트에서 읽음 |

`SQL_NOT_ANALYZED` 가 0 이라는 것은 B 계층이 이 합성 구문에서 문장을 포기하지
않았다는 뜻이지, 고유쌍이 전부 맞다는 뜻은 아닙니다.

### 채점

```sh
cd plsql-lineage-corpus
python3 -m synplsql.score \
  --truth out/full/lineage_truth.json \
  --manifest out/full/manifest.json \
  --engine /tmp/engine-full.json \
  --format generic
```

채점은 **고유 `source → target` 쌍**입니다. 정답 raw 8,629 / 엔진 raw 7,780 이어도
쌍은 truth 993 / engine 1,027 입니다.

| | 값 |
|---|---|
| 파싱 성공률 | 100.0% (201/201) |
| 고유 쌍 | truth 993 / engine 1,027 (TP 977, FP 50, FN 16) |
| Precision / Recall / F1 | 95.1% / 98.4% / **96.7%** |
| Kind (정밀 / 개략) | 94.0% / 100.0% |
| 다홉 완주율 | 90.1% (1,758/1,950) |
| UNRESOLVED (P/R 제외) | 126 |

Tier별 (파일 범위 쌍, 같은 쌍이 여러 파일에 있으면 중복 집계):

| Tier | expected | P | R | F1 |
|---|---:|---:|---:|---:|
| 0 | 303 | 100.0% | 100.0% | 100.0% |
| 1 | 1,303 | 100.0% | 100.0% | 100.0% |
| 2 | 4,583 | 100.0% | 100.0% | 100.0% |
| 3 | 1,222 | 92.5% | 91.4% | **91.9%** |

엔진 kind 원본 건수: DIRECT 2,908, INDIRECT_FILTER 2,220, TRANSFORM 1,267,
VIA_VARIABLE 690, VIA_CTE 464, ANALYTIC 161, AGGREGATE 70.
정답 대비 INDIRECT_FILTER 가 적고 VIA_VARIABLE 이 많습니다. 고유쌍 FP 50 의
대부분은 `VIA_VARIABLE` 여분이고, FN 16 은 `MST_CODE.*` 필터 2쌍과
`PKG_INB_142` / `PKG_MST_143` / `PKG_MST_171` 의 TRANSFORM 누락입니다.

### 처리량 대비

| 숫자 | 무엇 | 출처 |
|---|---|---|
| 136 라인/s | 파서 콜드 (워밍업 포함) | `plsql-lineage-engine/README.md`, 2026-08-24 A 계층만 |
| **957 라인/s** | 파서 웜 (DFA 캐시) | 같은 README. 300k ≈ 워밍업 75s + 5분 추정의 근거 |
| **1,638 / 1,737 라인/s** | **A+B+C 엔진**, 이 런 | 위. 웜이 957 보다 빠름 — 이 머신이 파서만으로도 ~1,960 라인/s (300,612 / 153.1s) |
| 13 라인/s | 실무 표기 | 비공개 SQL. 이 런으로 재현하지 않음 |

합성 웜과 실무 13 라인/s 의 자릿수 차이는 그대로입니다. 30만 라인 추정치
(워밍업 75초 + 약 5분)는 **합성 코퍼스에서는 보수적**이었습니다 — 실제 워밍업은
첫 파일 10.7s, 전체 3분 3초. 실무 표기에서는 여전히 성립하지 않습니다.

한 프로세스 DFA 캐시는 측정으로 확인됩니다. `PlSqlParser.decisionsToDFA` 는
클래스 속성입니다. 첫 파일 44.4 라인/s vs 이후 1,737 라인/s (약 39배).
파일마다 프로세스를 나누면 워밍업을 매번 다시 뭅니다.

### 병목

벽시계의 83.5% 는 ANTLR 파싱입니다. sqlmap+dataflow 는 16.5% 이고, 파일
단위로도 rest 가 parse 를 넘는 경우는 거의 없습니다.

가장 느린 파일은 **큰 파일이 아니라 워밍업 구간의 작은 파일**입니다.

| 벽시계 | 라인 | 라인/s | parse | 파일 |
|---:|---:|---:|---:|---|
| 15.9s | 674 | 43 | 15.8s | `SYNWMS.PKG_ARC_014.sql` (알파 2번째, 워밍업) |
| 14.9s | 32,655 | **2,197** | 11.5s | `SYNWMS.PKG_OUT_130.sql` (최대 패키지, 웜) |
| 10.7s | 475 | 44 | 10.6s | `SYNWMS.PKG_ARC_007.sql` (첫 파일) |
| 8.5s | 710 | 83 | 8.4s | `SYNWMS.PKG_ARC_021.sql` |
| 6.8s | 14,590 | 2,143 | 5.3s | `SYNWMS.PKG_ARC_147.sql` |

같은 32,655 라인 파일을 별도 프로세스에서 작은 파일로만 워밍업한 뒤 두 번 돌리면:

| | 벽시계 | 라인/s | parse / rest |
|---|---:|---:|---|
| pass1 (DFA 부분 웜) | 33.26s | 982 | 29.96 / 3.31 |
| pass2 (같은 프로세스) | 16.50s | 1,980 | 13.09 / 3.41 |

작은 파일 하나로 워밍업하면 큰 패키지의 구문 결정이 아직 비어 있어 parse 가
두 배가 됩니다. 코퍼스 전체를 한 프로세스에서 알파순으로 돌릴 때 `PKG_OUT_130`
은 이미 웜이어서 14.9s 입니다.

`cProfile` (같은 파일 3번째 패스, 프로파일 오버헤드로 57s): 상위는 ANTLR
`IntervalSet` / `ParserATNSimulator.adaptivePredict` / `LexerATNSimulator` 와
`structure._find_all` 트리 순회입니다. **같은 파일을 두 번 파싱하거나 DFA 를
인스턴스마다 새로 만드는 구멍은 없습니다.** 여기 손대는 최적화는 문법/런타임
쪽이라 이 브랜치에서 큰 리팩터는 하지 않았습니다.

### 건너뛴 것

- **EAI 코퍼스** (`syneai.generate`). 이 엔진은 PL/SQL 만 읽습니다. 문서의
  EAI 488 엣지는 채점하지 않았습니다.
- **두 번째 201파일 프로세스**. 파일 1 vs 2–201 과 큰 패키지 pass1/pass2 로
  워밍업 효과를 이미 봤습니다. 새 프로세스는 첫 파일 워밍업(~11s)을 다시 뭅니다.
- **실무 13 라인/s 재현**. 비공개 SQL 이 필요합니다.

### 재실행 메모

`out/full/` 과 `/tmp/engine-full.json` 은 커밋하지 않습니다. 같은 명령을 다시
돌리면 됩니다. 타이머를 빼도 분석 결과는 같습니다 (`--progress` / `--timings`
생략).
