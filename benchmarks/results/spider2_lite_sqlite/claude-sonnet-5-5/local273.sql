WITH o0 AS (
  SELECT row_number() OVER (ORDER BY ordered, customer_id, product_id) AS rn,
         customer_id, ordered, product_id, product_name, qty
  FROM customer_order_products
),
o AS (
  SELECT rn, product_id, product_name, qty,
         SUM(qty) OVER (PARTITION BY product_id ORDER BY ordered, rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS to_qty
  FROM o0
),
o2 AS (
  SELECT rn, product_id, product_name, qty, to_qty - qty AS from_qty, to_qty
  FROM o
),
i AS (
  SELECT id, product_id,
         SUM(qty) OVER (PARTITION BY product_id ORDER BY purchased, qty, id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS to_qty,
         qty
  FROM inventory_with_dims
),
i2 AS (
  SELECT id, product_id, to_qty - qty AS from_qty, to_qty
  FROM i
),
picks AS (
  SELECT o2.rn, o2.product_name, o2.qty AS order_qty,
         COALESCE(SUM(
           CASE WHEN i2.id IS NOT NULL
                THEN min(o2.to_qty, i2.to_qty) - max(o2.from_qty, i2.from_qty)
           END), 0) AS picked
  FROM o2
  LEFT JOIN i2
    ON i2.product_id = o2.product_id
   AND i2.from_qty < o2.to_qty
   AND i2.to_qty > o2.from_qty
  GROUP BY o2.rn, o2.product_name, o2.qty
)
SELECT product_name,
       AVG(picked * 100.0 / order_qty) AS avg_pick_pct
FROM picks
GROUP BY product_name
ORDER BY product_name