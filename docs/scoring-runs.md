# 합성 코퍼스 채점 기록

엔진 로드맵의 현재 요약은 [engine-roadmap.md](engine-roadmap.md)에 있습니다.
이 문서는 **언제, 어떤 명령으로, 어떤 규모를 채점했는지**만 남깁니다.
합성 점수는 "이 구문 분포에서 이 정도"이지 실무 PL/SQL 일반화가 아닙니다
([validation-limits.md](validation-limits.md)).

생성물 `plsql-lineage-corpus/out/` 은 gitignore 입니다. 아래 숫자는 재생성하면
문장이 일대일로 대응하지 않습니다. `--input` 은 항상 코퍼스 **루트**입니다
(`packages/` 를 넘기면 `location.file` 이 정답셋과 어긋나 티어별 표가 0% 가 됩니다).

엔진 SHA: `27e04ef` (`main` 과 동일. MERGE / CTE / `SELECT *` 는 `6c6450b`,
상수 USING/CTE alias 수정은 `f6b7cdd`).

## 2026-08-26 — Tier 2, 21 패키지 / 30,130 라인 (JAC-159)

이전 공개 샘플은 16 패키지 / 24,992 라인이었습니다. 기본 30만 라인 코퍼스는
돌리지 않았습니다 (JAC-160).

```sh
cd plsql-lineage-corpus
python3 -m synplsql.generate --tier 2 --packages 20 --lines 30000 --out out/tier2
# 실제 산출: 21 패키지 / 30,130 라인 / 프로시저 59 / 함수 10 / 정답 엣지 937
# 종류: AGGREGATE 17, ANALYTIC 23, DIRECT 300, INDIRECT_FILTER 364,
#       TRANSFORM 180, VIA_CTE 53

cd ../plsql-lineage-engine
python3 scripts/build_parser.py
PYTHONPATH=. python3 -m plsqllineage.engine \
  --input ../plsql-lineage-corpus/out/tier2 --out /tmp/engine-t2.json
# 파싱 21/21, 엔진 엣지 853, 진단 0, 58.9s (~512 라인/s)

cd ../plsql-lineage-corpus
python3 -m synplsql.score \
  --truth out/tier2/lineage_truth.json --manifest out/tier2/manifest.json \
  --engine /tmp/engine-t2.json --format generic
```

| | 값 |
|---|---|
| 파싱 성공률 | 100.0% (21/21) |
| 고유 쌍 | truth 420 / engine 420 |
| Precision / Recall / F1 | 100.0% / 100.0% / 100.0% |
| Kind (정밀 / 개략) | 100.0% / 100.0% |
| 다홉 완주율 | 100.0% (206/206) |
| Tier 2 표 (엣지 959) | P/R/F1 100.0% |
| UNRESOLVED | 0 |

이 규모에서도 MERGE / CTE / `SELECT *` 실패 유형은 나오지 않았습니다.
**전체 기본 코퍼스(201 패키지 / ~300k 라인)는 아직 미실행**이므로 JAC-159 는
Done 이 아닙니다.

## 2026-08-26 — Tier 3, 21 패키지 / 30,029 라인

같은 날, 같은 엔진으로 비슷한 규모의 Tier 3 을 한 번 더 돌렸습니다.

```sh
cd plsql-lineage-corpus
python3 -m synplsql.generate --tier 3 --packages 20 --lines 30000 --out out/tier3
# 실제 산출: 21 패키지 / 30,029 라인 / 프로시저 62 / 함수 9 / 정답 엣지 857
# REF CURSOR 투영 19. VIA_VARIABLE 67, VIA_CTE 51, UNRESOLVED 13

cd ../plsql-lineage-engine
PYTHONPATH=. python3 -m plsqllineage.engine \
  --input ../plsql-lineage-corpus/out/tier3 --out /tmp/engine-t3.json
# 파싱 21/21, 엔진 엣지 778, 진단 0, 61.5s (~488 라인/s)

cd ../plsql-lineage-corpus
python3 -m synplsql.score \
  --truth out/tier3/lineage_truth.json --manifest out/tier3/manifest.json \
  --engine /tmp/engine-t3.json --format generic
```

| | 값 |
|---|---|
| 파싱 성공률 | 100.0% (21/21) |
| 고유 쌍 | truth 367 / engine 367 (TP 365, FP 2, FN 2) |
| Precision / Recall / F1 | 99.5% / 99.5% / 99.5% |
| Kind (정밀 / 개략) | 100.0% / 100.0% |
| 다홉 완주율 | 100.0% (199/199) |
| Tier 3 표 (엣지 811) | P/R/F1 98.5% |
| UNRESOLVED | 13 (P/R 제외. 동적 SQL 구간) |

이전 16 패키지 샘플(26,273 라인, 고유쌍 342)은 F1 99.3% / 다홉 162/162 였습니다.
이번 21 패키지 샘플은 고유쌍 F1 99.5%, 다홉 199/199 입니다. 코퍼스가 같아서가
아니라 티어와 규모가 비슷할 뿐입니다.

## 하지 않은 것

- **JAC-160** — 기본 201 패키지 / ~300,612 라인 전체 코퍼스는 생성·채점하지 않았습니다.
  실무 표기 처리량은 13 라인/s 로 이미 추정치가 빗나간 것이 확인돼 있고
  ([engine-roadmap.md](engine-roadmap.md) 2026-08-26 재측정), 이번 실행의 합성
  처리량은 약 500 라인/s 입니다.
- 생성 `out/` 은 커밋하지 않습니다.
