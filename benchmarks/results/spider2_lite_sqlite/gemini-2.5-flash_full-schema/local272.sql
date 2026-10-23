WITH OrderLinesWithRunningSum AS (
  SELECT
    ol.id AS orderline_id,
    ol.product_id,
    ol.qty AS ordered_qty,
    SUM(ol.qty) OVER (PARTITION BY ol.product_id ORDER BY ol.id) AS product_running_ordered_qty
  FROM main.orderlines AS ol
  WHERE
    ol.order_id = 423
),
OrderLinesForPicking AS (
  SELECT
    orderline_id,
    product_id,
    ordered_qty,
    product_running_ordered_qty,
    LAG(product_running_ordered_qty, 1, 0) OVER (PARTITION BY product_id ORDER BY orderline_id) AS product_prev_running_ordered_qty
  FROM OrderLinesWithRunningSum
),
InventoryWithRunningSum AS (
  SELECT
    i.product_id,
    i.location_id,
    i.aisle,
    i.position,
    i.qty AS available_qty,
    i.purchased,
    SUM(i.qty) OVER (PARTITION BY i.product_id ORDER BY i.purchased ASC, i.qty ASC, i.location_id ASC) AS product_running_available_qty
  FROM main.inventory_with_dims AS i
  WHERE
    i.warehouse = 1
),
InventoryForPicking AS (
  SELECT
    product_id,
    location_id,
    aisle,
    position,
    available_qty,
    purchased,
    product_running_available_qty,
    LAG(product_running_available_qty, 1, 0) OVER (PARTITION BY product_id ORDER BY purchased ASC, available_qty ASC, location_id ASC) AS product_prev_running_available_qty
  FROM InventoryWithRunningSum
)
SELECT
  ol.product_id,
  inv.aisle,
  inv.position,
  MIN(inv.product_running_available_qty, ol.product_running_ordered_qty) - MAX(inv.product_prev_running_available_qty, ol.product_prev_running_ordered_qty) AS qty_to_pick
FROM OrderLinesForPicking AS ol
JOIN InventoryForPicking AS inv
  ON ol.product_id = inv.product_id
WHERE
  inv.product_running_available_qty > ol.product_prev_running_ordered_qty AND
  ol.product_running_ordered_qty > inv.product_prev_running_available_qty AND
  (MIN(inv.product_running_available_qty, ol.product_running_ordered_qty) - MAX(inv.product_prev_running_available_qty, ol.product_prev_running_ordered_qty)) > 0
ORDER BY
  ol.product_id,
  ol.orderline_id,
  inv.purchased ASC,
  inv.available_qty ASC,
  inv.location_id ASC