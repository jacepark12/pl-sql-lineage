# 파싱 완료 보고서

엔진은 파일을 읽을 때마다 단계 시간을 남기고, 런이 끝나면 한 장의 완료
보고서를 출력합니다. 엣지 JSON 계약은 그대로입니다.

## 명령

```sh
cd plsql-lineage-engine
PYTHONPATH=. python3 -m plsqllineage.engine \
  --input ../plsql-lineage-corpus/out \
  --out /tmp/engine.json \
  --progress \
  --report /tmp/parse-report.txt \
  --report-json /tmp/parse-report.json \
  --timings /tmp/timings.json
```

`--progress` 는 파일마다 `lex` / `antlr` / `sqlmap` 을 stderr 에 찍습니다.
`--report` 는 사람이 읽는 완료 보고서, `--report-json` 은 같은 내용의 JSON,
`--timings` 는 파일별 샘플입니다. 플래그 없이도 완료 보고서는 stderr 로
나갑니다. 마지막 줄은 항상 다음 형식입니다.

```
PARSE_COMPLETE files=201/201 lines=300612 elapsed=182.321s parse=149.582s rest=32.696s edges=7813 diagnostics=548 ok=1
```

`ok=1` 은 `PARSE_FAILED` 와 `DECODE_FAILED` 가 0 이라는 뜻입니다.

## 단계

| 이름 | 구간 |
|---|---|
| `decode` | utf-8 / cp949 읽기 |
| `wrap` | `ALL_SOURCE` 용 `CREATE OR REPLACE` 접두 |
| `lex` | ANTLR 토큰화 (`CommonTokenStream.fill`) |
| `antlr` | `sql_script()` — SLL+bail, 취소 시 LL 재시도 |
| `extract` | 패키지·프로시저·문장 범위 (A층) |
| `sqlmap` | 문장 컬럼 리니지 + `%ROWTYPE` / 루프 투영 (B층) |
| `dataflow` | 변수 스코프와 엣지 해소 (C층) |
| `catalog` | `ddl/catalog.sql` 로드 (런 1회) |

`parse` = decode+wrap+lex+antlr, `rest` = extract+sqlmap+dataflow 입니다.
이전 `--timings` 의 `parse_s` / `rest_s` 와 같은 합입니다.

## 보고서를 보는 법

- **단계별 시간** 의 `<< 병목` 이 벽시계에서 가장 큰 구간입니다.
- **워밍업** 은 첫 파일 vs 이후입니다. ANTLR DFA 는 파서 클래스에 남습니다.
  앞쪽 작은 파일이 벽시계 상단에 있어도 라인/s 가 웜 평균의 20% 미만이면
  `(워밍업)` 으로 표시합니다. 큰 파일의 라인/s 를 보세요.
- **정확도** 는 진단 코드 건수입니다. `SQL_NOT_ANALYZED` 는 B층이 문장을
  포기한 것이고, `PARSE_FAILED` 는 트리를 못 만든 것입니다.
- **가장 느린 문장** 은 sqlglot 비용이 큰 DML 부터 보여 줍니다.
- **권고** 는 위 숫자에서 만든 다음 작업 후보입니다. 고유쌍 F1 은
  `synplsql.score` 가 따로 냅니다.

## 측정 기록 — 2026-09-07, 기본 합성 코퍼스

`plsql-lineage-corpus/out` (seed `20260812`, 201 패키지 / 300,612 라인).
엔진 SHA 는 이 문서와 같은 커밋입니다. JAC-160 의 대략치(parse 83.5% /
sqlmap+dataflow 16.5%, 183.6s) 와 벽시계는 같고, 이번이 그 나머지를
단계로 나눈 첫 기록입니다.

```sh
cd plsql-lineage-engine
PYTHONPATH=. python3 -m plsqllineage.engine \
  --input ../plsql-lineage-corpus/out \
  --out /tmp/engine.json \
  --progress --report /tmp/parse-report.txt --report-json /tmp/parse-report.json
cd ../plsql-lineage-corpus
python3 -m synplsql.score \
  --truth out/lineage_truth.json --manifest out/manifest.json \
  --engine /tmp/engine.json --format generic
```

### 속도

| | 값 |
|---|---|
| 벽시계 | **182.321s** (1,648.8 라인/s) |
| 파싱 | **201/201** (`PARSE_FAILED` 0, `DECODE_FAILED` 0) |
| 토큰 / 문장 | 2,516,034 / 86,280 |
| 엔진 엣지 | 7,813 |
| 진단 | 548 |
| 카탈로그 | 36 테이블, 0.000s |
| 첫 파일 (워밍업) | `PKG_ARC_007.sql` 10.601s, 44.8 라인/s |
| 이후 200 파일 | 171.677s, **1,748.3 라인/s** |

단계별 시간:

| 단계 | 초 | 벽시계 비율 |
|---|---:|---:|
| `antlr` (`sql_script` SLL) | 131.224 | **72.0%** ← 병목 |
| `extract` | 21.745 | 11.9% |
| `lex` | 18.207 | 10.0% |
| `dataflow` | 8.698 | 4.8% |
| `sqlmap` | 2.192 | 1.2% |
| `decode` + `wrap` + `catalog` | 0.017 | 0.0% |

이전 기록의 `rest` 16.5% 는 거의 전부 sqlmap 이 아니었습니다.
`extract`(트리 보행) 11.9% + `dataflow` 4.8% + `sqlmap` 1.2% 입니다.
문장 하나당 sqlglot 은 최대 5ms 수준이라 B층은 이 코퍼스에서 병목이 아닙니다.

벽시계 상단의 작은 패키지(`PKG_ARC_014` 674라인 / 16.6s, `PKG_ARC_007`
475라인 / 10.6s) 는 라인/s 가 웜 평균의 3% 미만입니다. DFA 가 아직
채워지는 구간입니다. 워밍업 이후 실제로 비싼 파일은
`PKG_OUT_130` (32,655 라인, 15.1s, 2,168 라인/s) 입니다.

### 정확도

| | 값 |
|---|---|
| 파싱 성공률 | 100.0% (201/201) |
| 고유 쌍 | truth 993 / engine 1,030 (TP 979, FP 51, FN 14) |
| Precision / Recall / F1 | 95.0% / 98.6% / **96.8%** |
| Kind (정밀 / 개략) | 94.0% / 100.0% |
| 다홉 완주율 | 90.1% (1,758/1,950) |
| `SQL_NOT_ANALYZED` | **0** |

진단 코드:

| code | 건수 | 내용 |
|---|---:|---|
| `UNRESOLVED` | 315 | 시퀀스·전역·레코드 필드 |
| `DYNAMIC_SQL` | 126 | 생성기 `EXEC_IMMEDIATE` 와 일치. 엣지 없음이 정상 |
| `PARAMETER_UNRESOLVED` | 107 | 파일 밖 호출자 |

Tier별 (파일 범위 쌍):

| Tier | expected | P | R | F1 |
|---|---:|---:|---:|---:|
| 0 | 303 | 100.0% | 100.0% | 100.0% |
| 1 | 1,303 | 100.0% | 100.0% | 100.0% |
| 2 | 4,583 | 100.0% | 100.0% | 100.0% |
| 3 | 1,222 | 92.4% | 93.4% | **92.9%** |

### 다음에 손댈 곳

속도: ANTLR `sql_script()` 가 72% 이므로 파일별 프로세스 분리는 금지에
가깝습니다. 문법 DFA 를 한 프로세스에 유지하는 것이 1,748 라인/s 의
전제입니다. 그다음이 `extract` 12% 입니다. sqlglot 최적화는 이 코퍼스에서
이득이 거의 없습니다.

정확도: 파싱과 문장 포기는 이미 0 입니다. 남는 것은 Tier 3 고유쌍
(매개변수·레코드·전역) 과 다홉 90.1% 입니다.
