CREATE TABLE customers (
  customer_id NUMBER PRIMARY KEY,
  region_code VARCHAR2(10),
  status VARCHAR2(20)
);

CREATE TABLE orders (
  order_id NUMBER PRIMARY KEY,
  customer_id NUMBER,
  order_amount NUMBER,
  order_status VARCHAR2(20)
);

CREATE TABLE customer_order_summary (
  customer_id NUMBER,
  region_code VARCHAR2(10),
  total_amount NUMBER,
  order_count NUMBER
);

INSERT INTO customer_order_summary (
  customer_id,
  region_code,
  total_amount,
  order_count
)
SELECT
  c.customer_id,
  c.region_code,
  SUM(o.order_amount) AS total_amount,
  COUNT(*) AS order_count
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id
WHERE c.status = 'ACTIVE'
  AND o.order_status = 'COMPLETE'
GROUP BY c.customer_id, c.region_code;

