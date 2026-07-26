CREATE TABLE sales_stage (
  sale_id NUMBER,
  customer_id NUMBER,
  amount NUMBER
);

CREATE TABLE sales_fact (
  sale_id NUMBER,
  customer_id NUMBER,
  amount NUMBER,
  batch_id NUMBER
);

CREATE OR REPLACE PROCEDURE load_sales(p_batch_id NUMBER, p_table_name VARCHAR2) IS
  v_sql CLOB;
  v_unresolved CLOB;
BEGIN
  v_sql :=
    'INSERT INTO sales_fact (sale_id, customer_id, amount, batch_id) ' ||
    'SELECT sale_id, customer_id, amount, :batch_id FROM sales_stage';

  EXECUTE IMMEDIATE v_sql USING p_batch_id;

  v_unresolved := 'DELETE FROM ' || p_table_name || ' WHERE batch_id = :batch_id';
  EXECUTE IMMEDIATE v_unresolved USING p_batch_id;
END load_sales;
/

