CREATE TABLE order_lines (
  order_id NUMBER,
  product_id NUMBER,
  quantity NUMBER,
  unit_price NUMBER
);

CREATE TABLE products (
  product_id NUMBER PRIMARY KEY,
  category_code VARCHAR2(30)
);

CREATE OR REPLACE VIEW category_sales_v AS
WITH line_amounts AS (
  SELECT
    ol.order_id,
    p.category_code,
    ol.quantity * ol.unit_price AS line_amount
  FROM order_lines ol
  JOIN products p
    ON p.product_id = ol.product_id
)
SELECT
  category_code,
  SUM(line_amount) AS gross_sales
FROM line_amounts
GROUP BY category_code;

