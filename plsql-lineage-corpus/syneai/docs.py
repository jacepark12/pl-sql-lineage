"""IS document types - the message schemas the pipeline carries between steps."""

from __future__ import annotations

from dataclasses import dataclass, field
from xml.sax.saxutils import escape

from .flow import DIM_ARRAY, DIM_SCALAR, Path, Seg, T_RECORD, T_RECREF, T_STRING

#: webMethods field type codes as they appear in a document type node.
FIELD_STRING = 0
FIELD_RECORD = 1


@dataclass
class DocType:
    """A document type with one repeating ``results`` record of scalar fields.

    That shape is what a JDBC Select adapter produces, and it is what makes the
    common MAPCOPY path three segments deep: document reference, then the
    results record, then the field.
    """

    name: str
    fields: list[str]
    comment: str = ""
    results_name: str = "results"
    package: str = ""
    #: Optional nested record inside ``results``. Its only purpose is to make
    #: some MAPCOPY paths four segments deep, matching the measured depth mix.
    nested_name: str = ""
    nested_fields: list[str] = field(default_factory=list)

    @property
    def ns(self) -> str:
        return f"{self.package}.docs:{self.name}" if self.package else f"docs:{self.name}"

    def root(self) -> Path:
        """``/<DOC>;4;0;<nsref>`` - the document reference segment."""

        return Path((Seg(self.name, T_RECREF, DIM_SCALAR, self.ns),))

    def results(self, as_array: bool = False) -> Path:
        dim = DIM_ARRAY if as_array else DIM_SCALAR
        return self.root().child(Seg(self.results_name, T_RECORD, dim))

    def field(self, name: str, as_array: bool = False) -> Path:
        return self.results(as_array).child(Seg(name, T_STRING, DIM_SCALAR))

    def flat(self, name: str) -> Path:
        """``/<DOC>;2;0/<FIELD>;1;0`` - the document used as a plain record.

        Two segments rather than three: the target-side document is built in the
        pipeline rather than produced by an adapter, so it carries no document
        reference segment."""

        return Path((Seg(self.name, T_RECORD, DIM_SCALAR),
                     Seg(name, T_STRING, DIM_SCALAR)))

    def nested(self, name: str, as_array: bool = False) -> Path:
        """``/<DOC>;4;0;ns/results;2;0/<NESTED>;2;0/<FIELD>;1;0`` - four deep."""

        return (self.results(as_array)
                .child(Seg(self.nested_name, T_RECORD, DIM_SCALAR))
                .child(Seg(name, T_STRING, DIM_SCALAR)))

    def has(self, name: str) -> bool:
        return name in self.fields


def render_node_ndf(doc: DocType) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<Values version="2.0">',
        '  <value name="node_type">record</value>',
        f'  <value name="node_nsName">{escape(doc.ns)}</value>',
        f'  <value name="node_comment">{escape(doc.comment)}</value>',
        '  <value name="is_public">true</value>',
        '  <array name="rec_fields" depth="1" type="record"'
        ' javaclass="[Lcom.wm.util.Values;">',
        '    <record javaclass="com.wm.util.Values">',
        f'      <value name="field_name">{escape(doc.results_name)}</value>',
        f'      <value name="field_type">{FIELD_RECORD}</value>',
        '      <value name="field_dim">1</value>',
        '      <value name="field_opt">true</value>',
        '      <array name="rec_fields" depth="1" type="record"'
        ' javaclass="[Lcom.wm.util.Values;">',
    ]
    for name in doc.fields:
        lines += [
            '        <record javaclass="com.wm.util.Values">',
            f'          <value name="field_name">{escape(name)}</value>',
            f'          <value name="field_type">{FIELD_STRING}</value>',
            '          <value name="field_dim">0</value>',
            '          <value name="field_opt">true</value>',
            '        </record>',
        ]
    if doc.nested_name:
        lines += [
            '        <record javaclass="com.wm.util.Values">',
            f'          <value name="field_name">{escape(doc.nested_name)}</value>',
            f'          <value name="field_type">{FIELD_RECORD}</value>',
            '          <value name="field_dim">0</value>',
            '          <value name="field_opt">true</value>',
            '          <array name="rec_fields" depth="1" type="record"'
            ' javaclass="[Lcom.wm.util.Values;">',
        ]
        for name in doc.nested_fields:
            lines += [
                '            <record javaclass="com.wm.util.Values">',
                f'              <value name="field_name">{escape(name)}</value>',
                f'              <value name="field_type">{FIELD_STRING}</value>',
                '              <value name="field_dim">0</value>',
                '            </record>',
            ]
        lines += [
            '          </array>',
            '        </record>',
        ]
    lines += [
        '      </array>',
        '    </record>',
        '  </array>',
        '</Values>',
    ]
    return "\n".join(lines) + "\n"
