WITH ol AS (
  SELECT id AS orderline_id, product_id, qty,
         SUM(qty) OVER (PARTITION BY product_id ORDER BY id) AS cum_end
  FROM orderlines
  WHERE order_id = 423
),
ol2 AS (
  SELECT orderline_id, product_id, qty, cum_end, cum_end - qty AS cum_start
  FROM ol
),
inv AS (
  SELECT id AS inv_id, product_id, aisle, position, purchased, qty,
         SUM(qty) OVER (PARTITION BY product_id ORDER BY purchased, qty, id) AS cum_end
  FROM inventory_with_dims
  WHERE warehouse = 1
),
inv2 AS (
  SELECT inv_id, product_id, aisle, position, purchased, qty, cum_end, cum_end - qty AS cum_start
  FROM inv
)
SELECT ol2.orderline_id,
       ol2.product_id,
       inv2.aisle,
       inv2.position,
       MIN(ol2.cum_end, inv2.cum_end) - MAX(ol2.cum_start, inv2.cum_start) AS pick_qty
FROM ol2
JOIN inv2
  ON inv2.product_id = ol2.product_id
 AND inv2.cum_start < ol2.cum_end
 AND inv2.cum_end > ol2.cum_start
ORDER BY ol2.product_id, ol2.orderline_id, inv2.purchased, inv2.qty, inv2.inv_id