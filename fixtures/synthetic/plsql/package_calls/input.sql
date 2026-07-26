CREATE TABLE audit_log (
  event_id NUMBER,
  entity_name VARCHAR2(128),
  entity_id NUMBER,
  created_at DATE
);

CREATE TABLE customer_events (
  event_id NUMBER,
  customer_id NUMBER,
  event_type VARCHAR2(30)
);

CREATE OR REPLACE PACKAGE audit_pkg AS
  PROCEDURE write_event(p_entity_name VARCHAR2, p_entity_id NUMBER);
END audit_pkg;
/

CREATE OR REPLACE PACKAGE BODY audit_pkg AS
  PROCEDURE write_event(p_entity_name VARCHAR2, p_entity_id NUMBER) IS
  BEGIN
    INSERT INTO audit_log (
      event_id,
      entity_name,
      entity_id,
      created_at
    ) VALUES (
      audit_seq.NEXTVAL,
      p_entity_name,
      p_entity_id,
      SYSDATE
    );
  END write_event;
END audit_pkg;
/

CREATE OR REPLACE PACKAGE customer_event_pkg AS
  PROCEDURE record_event(p_customer_id NUMBER, p_event_type VARCHAR2);
END customer_event_pkg;
/

CREATE OR REPLACE PACKAGE BODY customer_event_pkg AS
  PROCEDURE record_event(p_customer_id NUMBER, p_event_type VARCHAR2) IS
  BEGIN
    INSERT INTO customer_events (
      event_id,
      customer_id,
      event_type
    ) VALUES (
      customer_event_seq.NEXTVAL,
      p_customer_id,
      p_event_type
    );

    audit_pkg.write_event('CUSTOMER', p_customer_id);
  END record_event;
END customer_event_pkg;
/

