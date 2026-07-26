CREATE TABLE order_totals (
  order_id NUMBER,
  net_amount NUMBER
);

CREATE OR REPLACE PACKAGE pricing_pkg AS
  FUNCTION net_amount(p_gross NUMBER, p_discount NUMBER) RETURN NUMBER;
  PROCEDURE store_total(
    p_order_id NUMBER,
    p_gross NUMBER,
    p_discount NUMBER
  );
END pricing_pkg;
/

CREATE OR REPLACE PACKAGE BODY pricing_pkg AS
  FUNCTION net_amount(p_gross NUMBER, p_discount NUMBER) RETURN NUMBER IS
  BEGIN
    RETURN p_gross - p_discount;
  END net_amount;

  PROCEDURE store_total(
    p_order_id NUMBER,
    p_gross NUMBER,
    p_discount NUMBER
  ) IS
  BEGIN
    INSERT INTO order_totals (
      order_id,
      net_amount
    ) VALUES (
      p_order_id,
      pricing_pkg.net_amount(p_gross, p_discount)
    );
  END store_total;
END pricing_pkg;
/
