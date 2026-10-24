WITH ol AS (
  SELECT id AS line_id, product_id, qty,
         SUM(qty) OVER (PARTITION BY product_id ORDER BY id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_qty
  FROM orderlines
  WHERE order_id = 423
), ol2 AS (
  SELECT line_id, product_id, qty, cum_qty, cum_qty - qty AS prev_cum
  FROM ol
), inv AS (
  SELECT i.product_id, i.location_id, i.aisle, i.position, i.purchased, i.qty,
         SUM(i.qty) OVER (PARTITION BY i.product_id ORDER BY i.purchased, i.qty, i.id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_qty,
         ROW_NUMBER() OVER (PARTITION BY i.product_id ORDER BY i.purchased, i.qty, i.id) AS inv_seq
  FROM inventory_with_dims i
  WHERE i.warehouse = 1
    AND i.product_id IN (SELECT product_id FROM orderlines WHERE order_id = 423)
), inv2 AS (
  SELECT product_id, location_id, aisle, position, purchased, qty, inv_seq, cum_qty, cum_qty - qty AS prev_cum
  FROM inv
)
SELECT o.product_id,
       v.aisle,
       v.position,
       MIN(o.cum_qty, v.cum_qty) - MAX(o.prev_cum, v.prev_cum) AS pick_qty
FROM ol2 o
JOIN inv2 v
  ON v.product_id = o.product_id
 AND v.prev_cum < o.cum_qty
 AND v.cum_qty > o.prev_cum
WHERE MIN(o.cum_qty, v.cum_qty) - MAX(o.prev_cum, v.prev_cum) > 0
ORDER BY o.line_id, v.inv_seq