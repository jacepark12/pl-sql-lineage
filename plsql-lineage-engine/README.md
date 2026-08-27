# PL/SQL 리니지 엔진

Oracle PL/SQL 소스에서 컬럼 레벨 리니지를 추출합니다. 설계 근거와 측정은
[../docs/engine-architecture.md](../docs/engine-architecture.md)에 있습니다.

## 준비

파서는 생성물이라 커밋되어 있지 않습니다. 최초 1회 생성해야 합니다.

```sh
pip install -r <(python3 -c "import tomllib,sys;print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))")
python3 scripts/build_parser.py      # java 필요. 10초 내외
```

`scripts/build_parser.py` 는 Maven Central 에서 ANTLR 도구를, raw.githubusercontent
에서 grammars-v4 의 PL/SQL 문법을 받아 `plsqllineage/_generated/` 에 Python 파서를
만듭니다(약 8 MB, `.gitignore` 대상).

문법에는 Java 문법으로 쓰인 액션이 들어 있어 Python 타깃에서 그대로 깨집니다.
빌드 스크립트가 매번 두 가지를 기계적으로 고칩니다 — `&&` → `and`, `this.` → `self.`.
원본 문법은 수정하지 않습니다.

## 사용

문장 단위 분석:

```python
from plsqllineage.sqlmap import analyze

result = analyze("MERGE INTO t USING s ON (t.k = s.k) WHEN MATCHED THEN UPDATE SET t.a = s.a")
```

파일 트리 분석. 코퍼스 루트를 넘기면 `packages/*.sql` 만 읽고 `ddl/catalog.sql` 은
`SELECT *` 전개에 씁니다.

```sh
python3 -m plsqllineage.engine --input ../plsql-lineage-corpus/out/dev --out /tmp/engine.json
```

```python
from plsqllineage.parser import parse_file

result = parse_file("SYNWMS.PKG_IFC_001.sql")
print(result.ok, len(result.problems))
```

대소문자는 신경 쓰지 않아도 됩니다. 문법은 대문자 키워드만 인식하지만
`CaseInsensitiveStream` 이 렉서가 **비교하는** 문자만 대문자로 바꾸고, 트리가 돌려주는
원문은 그대로 둡니다. 소스를 통째로 대문자로 올리면 문자열 리터럴이 손상됩니다.

## 뷰어 exporter

엔진 JSON(`edges` / `diagnostics`)은 정답셋과 같은 모양입니다. `web/index.html` 은
`objects` / `relationships` / `diagnostics` 를 읽습니다. 그 투영입니다.

```sh
# 엔진이 바로 뷰어 JSON 을 쓰게
python3 -m plsqllineage.engine --input ../plsql-lineage-corpus/out/dev \
  --out /tmp/viewer.json --format viewer

# 이미 뽑아 둔 엔진 JSON
python3 -m plsqllineage.export --input /tmp/engine.json --out /tmp/viewer.json
```

결과 파일을 뷰어 Explorer 의 Open JSON 으로 올리면 됩니다. 샘플:
`tests/fixtures/engine_sample.json` → `tests/fixtures/viewer_sample.json`.

| 엔진 `kind` | 뷰어 `relationships[].type` |
|---|---|
| `DIRECT`, `TRANSFORM`, `AGGREGATE`, `ANALYTIC`, `VIA_VARIABLE`, `VIA_CTE`, `VIA_PIPELINE` | `direct` |
| `INDIRECT_FILTER` 및 기타 비값 흐름 (`CONSTANT`, `SEVERED`, …) | `indirect` |
| `UNRESOLVED`, `DYNAMIC_SQL` | `dynamic_sql` |
| `CALL` | `call` |

객체 ID 는 소문자로 고정됩니다.

- 컬럼 `column.<table>.<column>` — `name` 은 `TABLE.COLUMN` 이라 뷰어가 테이블 노드 아래 행으로 묶습니다
- 테이블 `table.<table>` (컬럼이 없는 필터 대상도 여기)
- 위치 정보가 있으면 `package.<package>`, `procedure.<package>.<procedure>`
- 소스가 없는 `UNRESOLVED` 는 `dynamic_statement` 노드를 만들어 연결합니다

진단은 `severity` / `code` / `message` 를 유지하고 `location` 을
`spanText` (`file:line PACKAGE.PROCEDURE`) 로 펼칩니다. 뷰어 Diagnostics 탭이 그 네 칸을 읽습니다.

## 성능

ANTLR 은 결정 DFA 를 파서 클래스에 캐시합니다. 첫 파일이 워밍업 비용을 전부 물고,
이후로는 10배 가까이 빨라집니다.

| | 처리량 |
|---|---|
| 콜드 (워밍업 포함) | 약 136 라인/s |
| 웜 (DFA 캐시) | 약 957 라인/s |

30만 라인 코퍼스 기준 워밍업 약 75초 + 5분 내외입니다. 한 프로세스에서 여러 파일을
연속 처리해야 이 이득을 봅니다.
