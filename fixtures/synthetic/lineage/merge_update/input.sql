CREATE TABLE customer_dim (
  customer_id NUMBER PRIMARY KEY,
  email VARCHAR2(100),
  last_order_date DATE,
  status VARCHAR2(20)
);

CREATE TABLE customer_stage (
  customer_id NUMBER,
  email VARCHAR2(100),
  last_order_date DATE,
  is_active CHAR(1)
);

MERGE INTO customer_dim d
USING customer_stage s
ON (d.customer_id = s.customer_id)
WHEN MATCHED THEN UPDATE SET
  d.email = s.email,
  d.last_order_date = s.last_order_date,
  d.status = CASE WHEN s.is_active = 'Y' THEN 'ACTIVE' ELSE 'INACTIVE' END
WHEN NOT MATCHED THEN INSERT (
  customer_id,
  email,
  last_order_date,
  status
) VALUES (
  s.customer_id,
  s.email,
  s.last_order_date,
  CASE WHEN s.is_active = 'Y' THEN 'ACTIVE' ELSE 'INACTIVE' END
);

UPDATE customer_dim d
SET d.status = 'STALE'
WHERE d.last_order_date < ADD_MONTHS(SYSDATE, -18);

