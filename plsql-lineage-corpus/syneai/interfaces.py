"""Interface assembly: documents, adapters, and the three FLOW services.

Each interface mirrors the shape of the sampled packages - a ``_source`` service
that runs the Select adapter, a ``_start`` service that sequences the work, and
a ``_target`` service that maps fields and runs the write adapter. The tier
decides how much of the hard machinery appears.

Two things here are driven by the measured profile rather than by convenience:
the mix of MAPCOPY source-path depths, and the ratio of the other step kinds to
MAPCOPY. Left alone, a generator produces almost only three-segment paths and
almost no MAPDELETE, which would quietly remove the two properties that make
this corpus worth having.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass, field

from synplsql import schema as S
from synplsql.core import Edge

from .adapters import Adapter, build_custom_sql, build_select, build_writer
from .docs import DocType
from .flow import (
    Branch,
    FlowService,
    Invoke,
    Loop,
    Map,
    MapCopy,
    MapDelete,
    MapInvoke,
    MapSet,
    Path,
    Sequence,
    Step,
    assign_step_paths,
    scalar,
)
from .pipeline import CLEAR_PIPELINE, Context, Pipeline, simulate

#: Transformers seen in the sample, with the share each takes of MAPINVOKE.
TRANSFORMERS: tuple[tuple[str, float, dict, str], ...] = (
    ("pub.string:substring", 0.20, {"fromIndex": "0", "toIndex": "100"}, "inString"),
    ("pub.string:replace", 0.20, {"searchString": " ", "replaceString": ""}, "inString"),
    ("pub.math:roundNumber", 0.18, {"precision": "3"}, "num"),
    ("pub.math:addInts", 0.18, {}, "num1"),
    ("PSUtilities.string:substringRT", 0.12, {"len": "20"}, "inString"),
    ("pub.string:numericFormat", 0.07, {"pattern": "#,##0.000"}, "num"),
    ("pub.string:tokenize", 0.05, {"delim": ","}, "inString"),
)

TX_START = "pub.art.transaction:startTransaction"
TX_COMMIT = "pub.art.transaction:commitTransaction"

#: Utility services a real flow calls constantly - logging, error handling,
#: formatting. None of them touch a database, so they carry no lineage, but they
#: are most of the INVOKE count and they are what a step-path coordinate has to
#: survive.
UTILITY_SERVICES = (
    "pub.flow:getLastError",
    "pub.flow:debugLog",
    "SYNCOM.util:writeIfLog",
    "pub.date:getCurrentDateString",
    "pub.string:trim",
    "SYNCOM.util:checkMandatory",
    "pub.flow:tracePipeline",
    "SYNCOM.util:nextSequence",
)

#: Pipeline scalars. Copies between these are the one-segment paths.
SCRATCH = ("dataCount", "prevCount", "baseYmd", "lastKey", "errCount", "jobId",
           "procFlag", "chkSum", "rowIdx", "statCd")


@dataclass
class BuiltInterface:
    name: str
    ns: str
    tier: int
    title: str
    spec: S.EaiInterface
    src_doc: DocType
    tgt_doc: DocType
    stg_doc: DocType
    adapters: dict[str, Adapter]
    services: list[FlowService]
    edges: list[Edge] = field(default_factory=list)
    severed_fields: list[str] = field(default_factory=list)
    depth_counts: Counter = field(default_factory=Counter)


def _doc_fields(spec: S.EaiInterface) -> list[str]:
    """Source columns the interface actually reads."""

    used = [c for c in spec.mapping.values() if not c.startswith("'")]
    for col, _, _ in spec.filters:
        if col not in used:
            used.append(col)
    for j in spec.joins:
        for left, _ in j.on:
            if left not in used:
                used.append(left)
    order = spec.source_columns()
    return sorted(set(used), key=lambda c: order.index(c) if c in order else 999)


def _chunk(steps: list[Step], size: int) -> list[list[Step]]:
    return [steps[i:i + size] for i in range(0, len(steps), size)] if steps else []


def build_interface(rng: random.Random, spec: S.EaiInterface, index: int,
                    tier: int, profile: dict) -> BuiltInterface:
    name = f"SYN_WMS_S_{index:04d}"
    ns = f"SYN.WMS.S{index:04d}"
    depth_mix = {int(k): v for k, v in profile["mapcopy_depth"].items()}
    ratios = profile["step_ratio_to_mapcopy"]

    src_fields = _doc_fields(spec)
    # The nested record holds columns the mapping does *not* use. Keeping mapped
    # columns out of it means every four-segment path comes from the depth
    # balancer, so the measured depth mix stays under control instead of being
    # decided by how many columns an interface happens to map.
    nested_fields = [c for c in spec.source_columns() if c not in src_fields][:2]
    src_doc = DocType(
        name=spec.doc_name,
        fields=list(src_fields),
        comment=f"{spec.title} 원천 레코드",
        package=name,
        nested_name="detail" if nested_fields else "",
        nested_fields=list(nested_fields),
    )
    tgt_doc = DocType(name=spec.target_table, fields=list(spec.mapping),
                      comment=f"{spec.title} 타깃 레코드", package=name)
    stg_doc = DocType(name=f"{spec.target_table}_STG", fields=list(spec.mapping),
                      comment=f"{spec.title} 중간 스테이징 레코드", package=name)

    def src_path(column: str) -> Path:
        return (src_doc.nested(column) if column in nested_fields
                else src_doc.field(column))

    select_fields = list(src_fields) + list(nested_fields)

    select = build_select(spec, {c: c for c in select_fields})
    writer = build_writer(spec, {col: col for col in spec.mapping})
    adapters = {select.name: select, writer.name: writer}

    depths: Counter[int] = Counter()
    severed: list[str] = []

    def copy(frm: Path, to: Path, comment: str | None = None) -> MapCopy:
        depths[frm.depth] += 1
        return MapCopy(frm, to, comment=comment)

    # ---- field mapping -------------------------------------------------------
    # A share of the fields go through a staging record. That is both what real
    # flows do and what produces two-segment source paths.
    mapped = [(t, s) for t, s in spec.mapping.items() if not s.startswith("'")]
    literals = [(t, s) for t, s in spec.mapping.items() if s.startswith("'")]
    staged = {t for t, _ in mapped[:max(1, len(mapped) // 3)]}

    direct_steps: list[Step] = []
    stage_in: list[Step] = []
    stage_out: list[Step] = []
    for tgt_col, src_col in mapped:
        if tgt_col in staged:
            stage_in.append(copy(src_path(src_col), stg_doc.flat(tgt_col)))
            stage_out.append(copy(stg_doc.flat(tgt_col), tgt_doc.flat(tgt_col)))
        else:
            direct_steps.append(copy(src_path(src_col), tgt_doc.flat(tgt_col)))

    literal_steps: list[Step] = [
        MapSet(tgt_doc.flat(t), s.strip("'")) for t, s in literals]

    # Audit copies: source fields lifted into scratch slots for logging and
    # validation. Real flows are full of these, and they are what keeps the
    # fixed per-interface constant count from dominating the MAPSET ratio on a
    # schema whose tables are narrower than the sampled ones.
    audit_steps: list[Step] = [
        copy(src_path(col), scalar(SCRATCH[i % len(SCRATCH)]))
        for i, col in enumerate(src_fields)
    ]

    # ---- depth balancing -----------------------------------------------------
    # Emit exactly as many housekeeping copies as the measured depth mix calls
    # for, given the mapping copies already fixed by the interface definition.
    house = _balance_depths(depths, depth_mix, src_doc, tgt_doc, nested_fields,
                            rng, copy)

    # ---- transformers and the consequential delete ---------------------------
    transform_steps: list[Step] = []
    delete_steps: list[Step] = []
    if tier >= 1:
        transform_steps = _transforms(rng, direct_steps or stage_out, tgt_doc,
                                      depths, 2 if tier < 2 else 4)
    if tier >= 2:
        # The delete that actually severs lineage stays a Tier 2 construct.
        delete_steps = _sever(rng, spec, tgt_doc, severed)

    # ---- target service ------------------------------------------------------
    body: list[Step] = []
    for group in _chunk(direct_steps, 3):
        body.append(Map(children=group, comment="원천 → 타깃 직접 매핑"))
    for group in _chunk(stage_in, 3):
        body.append(Map(children=group, comment="원천 → 스테이징"))
    for group in _chunk(stage_out, 3):
        body.append(Map(children=group, comment="스테이징 → 타깃"))
    for group in _chunk(audit_steps, 3):
        body.append(Map(children=group, comment="검증/로그용 필드 추출"))
    if literal_steps:
        body.append(Map(children=literal_steps, comment="상수 설정"))
    if transform_steps:
        body.append(Map(children=transform_steps, comment="인라인 변환기 적용"))
    if delete_steps:
        body.append(Map(children=delete_steps, comment="파이프라인 필드 제거"))

    if tier >= 2:
        body = [Loop(in_array=src_doc.results(as_array=True), children=body,
                     comment="조회 결과 배열 반복")]

    write_invoke = Invoke(f"{ns}.adpt:{writer.name}", adapter=writer.name,
                          comment=f"{spec.target} 적재")
    if tier >= 3:
        flag = scalar("procFlag")
        body.append(Map(children=[copy(tgt_doc.flat(list(spec.mapping)[0]), flag)],
                        comment="분기 판정값 산출"))
        body.append(Branch(switch=flag, cases=[
            ("$default", Sequence(name="write", children=[write_invoke])),
            ("SKIP", Sequence(name="skip",
                              children=[Map(children=[MapSet(scalar("errCount"), "1")])])),
        ], comment="조건부 적재"))
    else:
        body.append(write_invoke)

    target_children: list[Step] = [Invoke(TX_START, comment="트랜잭션 시작")]
    target_children += body
    target_children.append(Invoke(TX_COMMIT, comment="트랜잭션 종료"))
    for group in _chunk(house, 3):
        target_children.append(Map(children=group, comment="보조 계산"))

    if tier >= 3:
        custom = build_custom_sql(spec)
        adapters[custom.name] = custom
        target_children.append(Invoke(f"{ns}.adpt:{custom.name}", adapter=custom.name,
                                      comment="CustomSQL - 인터페이스 상태 갱신"))
        target_children.append(
            Invoke(CLEAR_PIPELINE, preserve=["dataCount", "errCount"],
                   comment="preserve 목록 외 파이프라인 전체 소거"))
        target_children.append(
            Invoke(f"{ns}.adpt:{writer.name}", adapter=writer.name,
                   comment="소거 후 재적재 - 이 시점 리니지는 끊겨 있어야 정답"))

    # Cleanup deletes. Most of them are harmless because they run after the
    # write; telling them apart from the one that matters needs step order.
    cleanup = [MapDelete(stg_doc.flat(t)) for t in list(staged)[:3]]
    cleanup += [MapDelete(scalar(n)) for n in SCRATCH[:_want(ratios, "MAPDELETE",
                                                             sum(depths.values()))
                                                     - len(cleanup) - len(delete_steps)]]
    for group in _chunk(cleanup, 3):
        target_children.append(Map(children=group, comment="파이프라인 정리"))

    target_steps: list[Step] = [Sequence(name="main", children=target_children)]

    # ---- source service ------------------------------------------------------
    source_steps: list[Step] = [Sequence(name="main", children=[
        Map(children=[MapSet(scalar("baseYmd"), "20260812"),
                      MapSet(scalar("jobId"), name)], comment="실행 파라미터 설정"),
        Invoke(f"{ns}.adpt:{select.name}", adapter=select.name,
               comment=f"{spec.source} 조회"),
        _count_block(rng, src_doc, src_path, src_fields, copy),
    ])]

    # ---- start service -------------------------------------------------------
    start_steps: list[Step] = [Sequence(name="main", children=[
        Invoke(f"{ns}.srvc:{name}_source", comment="원천 조회 호출"),
        Map(children=[copy(scalar("dataCount"), scalar("prevCount"))]),
        Invoke(f"{ns}.srvc:{name}_target", comment="매핑/적재 호출"),
    ])]

    per_service = profile["step_per_service"]
    services = [
        FlowService(f"{name}_source",
                    _wrap(source_steps, rng, per_service, rng.random() < 0.6),
                    f"{spec.title} 원천 조회"),
        FlowService(f"{name}_start",
                    _wrap(start_steps, rng, per_service, rng.random() < 0.6),
                    f"{spec.title} 제어"),
        FlowService(f"{name}_target",
                    _wrap(target_steps, rng, per_service, rng.random() < 0.6),
                    f"{spec.title} 매핑/적재"),
    ]
    for svc in services:
        assign_step_paths(svc.steps, f"{svc.name}/")

    built = BuiltInterface(
        name=name, ns=ns, tier=tier, title=spec.title, spec=spec,
        src_doc=src_doc, tgt_doc=tgt_doc, stg_doc=stg_doc, adapters=adapters,
        services=services, severed_fields=severed, depth_counts=depths,
    )

    # ---- truth ---------------------------------------------------------------
    def doc_path(adapter: Adapter, field_name: str) -> Path:
        if adapter is select:
            return src_path(field_name)
        return tgt_doc.flat(field_name)

    ctx = Context(interface=name, target_table=spec.target)
    pipe = Pipeline()
    edges: list[Edge] = []
    # The start service invokes source then target, so one pipeline carries
    # across both - replaying them separately would lose every edge.
    for svc in (services[0], services[2]):
        sub, pipe = simulate(svc.steps, ctx, adapters, doc_path, pipe)
        edges.extend(sub)
    built.edges = edges
    return built


def _count_block(rng: random.Random, src_doc: DocType, src_path, src_fields,
                 copy) -> Step:
    """Row-count summary. Looping over the result array is the common shape but
    not the only one, so the LOOP rate stays near the measured value."""

    inner = [Map(children=[copy(src_path(src_fields[0]), scalar("lastKey"))],
                 comment="행 단위 카운트"),
             Invoke("SYNCOM.util:nextSequence", comment="일련번호 채번")]
    if rng.random() < 0.45:
        return Loop(in_array=src_doc.results(as_array=True), children=inner,
                    comment="조회 결과 건수 집계")
    return Sequence(name="summary", children=inner, comment="조회 결과 요약")


def _count_kind(steps: list[Step], kind) -> int:
    total = 0
    for step in steps:
        if isinstance(step, kind):
            total += 1
        if isinstance(step, (Sequence, Map, Loop)):
            total += _count_kind(step.children, kind)
        elif isinstance(step, Branch):
            total += _count_kind([c for _, c in step.cases], kind)
    return total


def _wrap(steps: list[Step], rng: random.Random, per_service: dict,
          with_branch: bool = True) -> list[Step]:
    """Give a service the try/catch shape real FLOW services have, then pad the
    utility calls until the per-service INVOKE and SEQUENCE counts match."""

    inner = steps[0].children if len(steps) == 1 and isinstance(steps[0], Sequence) \
        else steps
    try_block = Sequence(name="try", exit_on="FAILURE", children=list(inner),
                         comment="정상 처리 구간")
    catch_block = Sequence(name="catch", exit_on="DONE", children=[
        Invoke("pub.flow:getLastError", comment="오류 정보 수집"),
        Invoke("SYNCOM.util:incErrCount", comment="오류 카운터 증가"),
    ], comment="예외 처리 구간")
    if with_branch:
        # A branch that only picks a logging path. It carries no lineage, and
        # telling it apart from the Tier 3 branch that gates a write is part of
        # what the corpus is testing.
        catch_block.children.append(Branch(switch=scalar("errCount"), cases=[
            ("$default", Sequence(name="warn", children=[
                Invoke("SYNCOM.util:writeIfLog", comment="경고 로그")])),
            ("0", Sequence(name="none", children=[
                Invoke("pub.flow:debugLog", comment="정상 종료 로그")])),
        ], comment="오류 건수에 따른 로그 분기"))
    root = Sequence(name="main", exit_on="DONE",
                    children=[try_block, catch_block])

    want_seq = int(round(per_service.get("SEQUENCE", 0)))
    while _count_kind([root], Sequence) < want_seq:
        try_block.children.append(Sequence(
            name=f"step{_count_kind([root], Sequence)}", exit_on="FAILURE",
            children=[Invoke(rng.choice(UTILITY_SERVICES), comment="후처리 단계")],
            comment="처리 단계 블록"))

    want_invoke = int(round(per_service.get("INVOKE", 0)))
    tail: list[Step] = []
    while _count_kind([root], Invoke) + len(tail) < want_invoke:
        tail.append(Invoke(rng.choice(UTILITY_SERVICES), comment="공통 유틸리티 호출"))
    try_block.children.extend(tail)
    return [root]


def _want(ratios: dict, kind: str, mapcopy_total: int) -> int:
    return max(0, round(ratios.get(kind, 0.0) * mapcopy_total))


def _balance_depths(depths: Counter, mix: dict[int, float], src_doc: DocType,
                    tgt_doc: DocType, nested_fields: list[str],
                    rng: random.Random, copy) -> list[Step]:
    """Add housekeeping copies until the source-path depth mix matches."""

    have3 = depths.get(3, 0)
    if not have3 or not mix.get(3):
        return []
    total = have3 / mix[3]
    out: list[Step] = []
    for depth in (1, 2, 4):
        need = int(round(mix.get(depth, 0.0) * total)) - depths.get(depth, 0)
        for i in range(max(0, need)):
            if depth == 1:
                frm = scalar(SCRATCH[i % len(SCRATCH)])
                to = scalar(SCRATCH[(i + 1) % len(SCRATCH)])
            elif depth == 2:
                names = tgt_doc.fields
                frm = tgt_doc.flat(names[i % len(names)])
                to = scalar(SCRATCH[i % len(SCRATCH)])
            else:
                if not nested_fields:
                    continue
                frm = src_doc.nested(nested_fields[i % len(nested_fields)])
                to = scalar(SCRATCH[i % len(SCRATCH)])
            out.append(copy(frm, to))
    return out


def _transforms(rng: random.Random, candidates: list[Step], tgt_doc: DocType,
                depths: Counter, count: int = 2) -> list[Step]:
    """Replace a couple of straight copies with an inline transformer."""

    picks = [s for s in candidates if isinstance(s, MapCopy)]
    if not picks:
        return []
    picks = rng.sample(picks, min(count, len(picks)))
    out: list[Step] = []
    for step in picks:
        service, weight, literals, in_name = _pick_transformer(rng)
        inputs = {in_name: step.frm}
        if service == "pub.math:addInts":
            inputs = {"num1": step.frm, "num2": step.frm}
        for _ in inputs:
            depths[step.frm.depth] += 1
        capped = dict(list(literals.items())[:1])
        out.append(MapInvoke(service=service, inputs=inputs, output=step.to,
                             output_name="value", literals=capped,
                             comment=f"{service} 변환 적용"))
    return out


def _pick_transformer(rng: random.Random):
    weights = [t[1] for t in TRANSFORMERS]
    return TRANSFORMERS[rng.choices(range(len(TRANSFORMERS)), weights=weights, k=1)[0]]


def _sever(rng: random.Random, spec: S.EaiInterface, tgt_doc: DocType,
           severed: list[str]) -> list[Step]:
    """Delete a non-key target field *before* the write.

    This is the discriminating case of the corpus. An engine that collects
    mappings without replaying step order still reports a source for this
    column; the truth says the lineage was cut here.
    """

    keys = set(spec.key_columns)
    candidates = [c for c in spec.mapping
                  if c not in keys and not spec.mapping[c].startswith("'")]
    if len(candidates) < 3:
        return []
    victim = rng.choice(candidates[2:])
    severed.append(victim)
    return [MapDelete(tgt_doc.flat(victim),
                      comment=f"{victim} 제거 - 이후 적재는 값 없음 (SEVERED)")]
