# Oracle PL/SQL Lineage MVP

Oracle SQL과 PL/SQL 파일에서 객체, 컬럼 계보, 서브프로그램 호출, 동적 SQL 위험을 추출하고 브라우저 그래프로 확인할 수 있는 실행형 MVP입니다.

## 바로 확인하기

전체 검증:

```sh
./gradlew check
```

SQL 파일 하나 분석:

```sh
./gradlew run --args="analyze \
  --input fixtures/synthetic/lineage/basic_insert_select/input.sql \
  --out reports/demo/basic_insert_select.json"
```

SQL 디렉터리 전체 분석:

```sh
./gradlew run --args="analyze \
  --input fixtures/public \
  --out reports/demo/public-corpus.json"
```

결과 화면:

```sh
open web/index.html
```

화면은 내장 데모 계보를 즉시 표시합니다. 왼쪽 `Explorer`의 `Open JSON`에서 생성한 JSON을 선택하면 실제 분석 결과로 교체됩니다.

## 사용자 관점의 제공 가치

- 변경 영향 분석: 소스 컬럼과 타깃 컬럼의 직접 계보를 확인합니다.
- SQLFlow형 그래프: 테이블과 뷰를 기본 노드로 표시하고 컬럼은 노드 내부 행으로 배치합니다.
- 탐색 중심 UI: 객체 트리, 계보 그래프, 선택 객체의 입출력 관계를 한 화면에서 함께 확인합니다.
- 데이터 품질 추적: `WHERE`, `JOIN`, `GROUP BY`, `MERGE ON`, `UPDATE WHERE`의 간접 영향을 구분합니다.
- PL/SQL 의존성: 패키지, 프로시저, 함수, 매개변수와 호출 관계를 확인합니다.
- 동적 SQL 위험: 문자열 리터럴 결합은 정적으로 복원하고, 객체명이 변수로 결정되는 SQL은 진단으로 표시합니다.
- 신뢰 경계: 해석하지 못한 동적 SQL과 일부 미지원 DML을 정상 결과처럼 숨기지 않고 진단으로 남깁니다.

## 현재 지원 범위

- 객체: `TABLE`, `VIEW`, `PACKAGE`, `PROCEDURE`, `FUNCTION`, `TRIGGER`, 매개변수, 동적 SQL 문장
- SQL 계보: `INSERT ... SELECT`, CTE 기반 뷰, `MERGE`, `UPDATE`, `INSERT ... VALUES`
- SQL 조건: 별칭, 직접 컬럼 표현식, 집계식, `JOIN`, `WHERE`, `GROUP BY`
- PL/SQL: 패키지/독립 프로시저와 함수 범위, 매개변수에서 테이블 컬럼으로의 흐름, 패키지 호출
- 동적 SQL: 리터럴 `||` 결합, `EXECUTE IMMEDIATE ... USING` 바인드 연결, 미해결 객체명 진단
- 입력: 단일 `.sql` 파일 또는 `.sql` 파일을 재귀 탐색하는 디렉터리
- 그래프: 테이블/뷰 안에 컬럼, 프로시저/함수 안에 매개변수를 중첩하고 엣지를 해당 행에 연결
- UI: 객체 트리나 그래프의 행을 선택하면 `Inspector`에서 소유 객체, 멤버, 입력/출력 관계와 표현식을 확인

이 구현은 Oracle 문법 전체를 처리하는 완전한 파서가 아닙니다. 균형 괄호와 리터럴/주석 인식 위에 의미 추출기를 둔 MVP이며, 복잡한 중첩 서브쿼리, 오버로드 해소, `q'[...]'` 문자열, 동적 PL/SQL 블록, 스키마 메타데이터 기반 동의어/DB 링크 해소는 후속 범위입니다.

## 검증 구성

`./gradlew check`는 다음을 모두 실행합니다.

- 합성 골든 픽스처 6개: 객체, 관계, 진단의 기대값 비교
- 이름 치환 변형 6개: 테이블/뷰/패키지/프로시저/함수명을 바꿔 하드코딩 여부 검사
- 공개 Oracle 코퍼스 15개: 객체/관계 유형, 최소 커버리지, 끊어진 엣지 검사
- ANTLR PL/SQL 예제 10개: PL/SQL 구조 강건성 및 호출 관계 검사

테스트 SQL의 출처, 고정 커밋, 용도 구분은 [docs/test-corpus.md](docs/test-corpus.md)에 정리되어 있습니다.

## 합성 코퍼스와 정답셋

`plsql-lineage-corpus/` 에 두 계층의 합성 코퍼스 생성기가 있습니다. 실제 자산의 구문
분포를 재현하되 업무 내용은 전부 가상이며, 소스와 리니지 정답을 같은 중간표현에서 동시에
생성하므로 라벨링 오류가 원천적으로 없습니다.

| 계층 | 대상 | 규모 |
|---|---|---|
| PL/SQL | Oracle 패키지 | 201 패키지 / 30만 라인 / 엣지 8,629 |
| EAI | webMethods 인터페이스 | 40 인터페이스 / 아티팩트 486 / 엣지 488 |

두 계층은 인터페이스 테이블에서 접합되어, 원천 시스템 → EAI → 인터페이스 테이블 →
PL/SQL → 리포트로 이어지는 **15홉 리니지 체인**을 만듭니다.

```sh
cd plsql-lineage-corpus
python3 -m synplsql.generate --out out --stats
python3 -m syneai.generate --out out/eai --merge out --stats
python3 -m synplsql.validate --out out && python3 -m syneai.validate --out out/eai
```

현재 분석기를 PL/SQL 코퍼스에 투입한 기준선은 엣지 F1 70.7%, 다홉 완주율 23.6%입니다.
EAI 계층은 아직 이 분석기의 지원 범위 밖입니다.
자세한 내용은 [plsql-lineage-corpus/README.md](plsql-lineage-corpus/README.md)를 보십시오.

## JSON 계약

- `objects`: 테이블, 컬럼, 뷰, 패키지, 프로시저, 함수, 매개변수, 트리거, 동적 문장
- `relationships`: `direct`, `indirect`, `call`, `dynamic_sql`
- `diagnostics`: 심각도, 코드, 메시지, 문제가 된 SQL 조각

구현 구조와 다음 단계는 [docs/mvp-implementation.md](docs/mvp-implementation.md)를 참고하십시오.
