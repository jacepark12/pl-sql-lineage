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
PARSE_COMPLETE files=201/201 lines=300612 elapsed=183.563s parse=153.130s rest=30.310s edges=7780 diagnostics=548 ok=1
```

`ok=1` 은 `PARSE_FAILED` 와 `DECODE_FAILED` 가 0 이라는 뜻입니다.

## 단계

| 이름 | 구간 |
|---|---|
| `decode` | utf-8 / cp949 읽기 |
| `wrap` | `ALL_SOURCE` 용 `CREATE OR REPLACE` 접두 |
| `lex` | ANTLR 토큰화 (`CommonTokenStream.fill`) |
| `antlr` | `sql_script()` SLL 파싱 |
| `extract` | 패키지·프로시저·문장 범위 (A층) |
| `sqlmap` | 문장 컬럼 리니지 + `%ROWTYPE` / 루프 투영 (B층) |
| `dataflow` | 변수 스코프와 엣지 해소 (C층) |
| `catalog` | `ddl/catalog.sql` 로드 (런 1회) |

`parse` = decode+wrap+lex+antlr, `rest` = extract+sqlmap+dataflow 입니다.
이전 `--timings` 의 `parse_s` / `rest_s` 와 같은 합입니다.

## 보고서를 보는 법

- **단계별 시간** 의 `<< 병목` 이 벽시계에서 가장 큰 구간입니다.
- **워밍업** 은 첫 파일 vs 이후입니다. ANTLR DFA 는 파서 클래스에 남습니다.
- **정확도** 는 진단 코드 건수입니다. `SQL_NOT_ANALYZED` 는 B층이 문장을
  포기한 것이고, `PARSE_FAILED` 는 트리를 못 만든 것입니다.
- **가장 느린 문장** 은 sqlglot 비용이 큰 DML 부터 보여 줍니다.
- **권고** 는 위 숫자에서 만든 다음 작업 후보입니다. 고유쌍 F1 은
  `synplsql.score` 가 따로 냅니다.

## 측정 기록

합성 코퍼스 `out/` (seed `20260812`, 201 패키지 / 300,612 라인) 을 이
계측으로 다시 돈 결과는 아래 커밋에서 채웁니다. 이전 대략치는
[scoring-runs.md](scoring-runs.md) 의 JAC-160 (parse 83.5% /
sqlmap+dataflow 16.5%) 입니다.
