"""Package-level nodes: the interface descriptor and FLOW service signatures."""

from __future__ import annotations

from xml.sax.saxutils import escape

from .flow import FlowService


def render_node_idf(interface_name: str, ns: str, title: str, tier: int) -> str:
    """``node.idf`` - the interface node that names the package namespace."""

    return "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<Values version="2.0">',
        '  <value name="node_type">interface</value>',
        f'  <value name="node_pkg">{escape(interface_name)}</value>',
        f'  <value name="node_nsName">{escape(ns)}</value>',
        f'  <value name="node_comment">{escape(title)} (Tier {tier})</value>',
        '  <value name="node_gen">합성 코퍼스 자동 생성. 실제 연계가 아닙니다.</value>',
        '  <value name="is_public">true</value>',
        '</Values>',
    ]) + "\n"


def render_service_ndf(service: FlowService, ns: str) -> str:
    """``node.ndf`` for a FLOW service - the signature beside its flow.xml."""

    return "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<Values version="2.0">',
        '  <value name="node_type">service</value>',
        '  <value name="svc_type">flow</value>',
        '  <value name="svc_subtype">unknown</value>',
        f'  <value name="node_nsName">{escape(ns)}:{escape(service.name)}</value>',
        f'  <value name="node_comment">{escape(service.comment)}</value>',
        '  <value name="is_public">true</value>',
        '  <record name="sig" javaclass="com.wm.util.Values">',
        '    <record name="in" javaclass="com.wm.util.Values">',
        '      <array name="rec_fields" depth="1" type="record"'
        ' javaclass="[Lcom.wm.util.Values;">',
        '        <record javaclass="com.wm.util.Values">',
        '          <value name="field_name">baseYmd</value>',
        '          <value name="field_type">0</value>',
        '          <value name="field_dim">0</value>',
        '        </record>',
        '      </array>',
        '    </record>',
        '    <record name="out" javaclass="com.wm.util.Values">',
        '      <array name="rec_fields" depth="1" type="record"'
        ' javaclass="[Lcom.wm.util.Values;">',
        '        <record javaclass="com.wm.util.Values">',
        '          <value name="field_name">dataCount</value>',
        '          <value name="field_type">0</value>',
        '          <value name="field_dim">0</value>',
        '        </record>',
        '      </array>',
        '    </record>',
        '  </record>',
        '</Values>',
    ]) + "\n"
