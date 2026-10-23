WITH ProductOrdersBase AS (
  SELECT
    cop.product_id,
    cop.product_name,
    cop.ordered AS order_date,
    cop.qty AS ordered_qty,
    -- Assign a unique identifier for each order line item to ensure stable ordering
    -- This order is crucial for FIFO and running sums
    ROW_NUMBER() OVER (PARTITION BY cop.product_id ORDER BY cop.ordered, cop.customer_id, cop.product_id) AS order_sequence,
    cop.customer_id -- Include customer_id for consistent ordering in subsequent steps
  FROM main.customer_order_products AS cop
),
ProductOrdersWithRunningTotals AS (
  SELECT
    pob.product_id,
    pob.product_name,
    pob.order_date,
    pob.ordered_qty,
    pob.order_sequence,
    -- Calculate running total of ordered quantity for each product
    SUM(pob.ordered_qty) OVER (PARTITION BY pob.product_id ORDER BY pob.order_sequence) AS running_ordered_qty
  FROM ProductOrdersBase AS pob
),
ProductOrdersWithPrev AS (
  SELECT
    powrt.product_id,
    powrt.product_name,
    powrt.order_date,
    powrt.ordered_qty,
    powrt.order_sequence,
    powrt.running_ordered_qty,
    -- Calculate the running total of ordered quantity *before* the current order line
    LAG(powrt.running_ordered_qty, 1, 0) OVER (PARTITION BY powrt.product_id ORDER BY powrt.order_sequence) AS prev_running_ordered_qty
  FROM ProductOrdersWithRunningTotals AS powrt
),
ProductInventoryBase AS (
  SELECT
    iwd.product_id,
    iwd.product_name,
    iwd.purchased AS purchase_date,
    iwd.qty AS inventory_qty,
    -- Order by purchase date (FIFO) and then by smallest quantity (as per requirement)
    -- Ensure stable, unique order for each inventory item within a product.
    ROW_NUMBER() OVER (PARTITION BY iwd.product_id ORDER BY iwd.purchased, iwd.qty, iwd.id) AS inventory_sequence
  FROM main.inventory_with_dims AS iwd
),
ProductInventoryWithRunningTotals AS (
  SELECT
    pib.product_id,
    pib.product_name,
    pib.purchase_date,
    pib.inventory_qty,
    pib.inventory_sequence,
    -- Calculate running total of inventory quantity for each product, ordered by purchase date (FIFO) and then by smallest quantity
    SUM(pib.inventory_qty) OVER (PARTITION BY pib.product_id ORDER BY pib.inventory_sequence) AS running_inventory_qty
  FROM ProductInventoryBase AS pib
),
ProductInventoryWithPrev AS (
  SELECT
    piwrt.product_id,
    piwrt.product_name,
    piwrt.purchase_date,
    piwrt.inventory_qty,
    piwrt.inventory_sequence,
    piwrt.running_inventory_qty,
    -- Calculate the running total of inventory quantity *before* the current inventory item
    LAG(piwrt.running_inventory_qty, 1, 0) OVER (PARTITION BY piwrt.product_id ORDER BY piwrt.inventory_sequence) AS prev_running_inventory_qty
  FROM ProductInventoryWithRunningTotals AS piwrt
),
OrderAllocations AS (
  SELECT
    powp.product_id,
    powp.product_name,
    powp.order_sequence,
    powp.ordered_qty,
    -- Calculate the picked quantity for each order line item by finding the overlap between
    -- the order's quantity range and the inventory item's quantity range.
    -- This simulates allocating inventory to orders based on the running totals.
    SUM(
      MAX(0,
        MIN(powp.running_ordered_qty, piwp.running_inventory_qty) -
        MAX(powp.prev_running_ordered_qty, piwp.prev_running_inventory_qty)
      )
    ) AS picked_qty_for_this_order_line
  FROM ProductOrdersWithPrev AS powp
  JOIN ProductInventoryWithPrev AS piwp
    ON powp.product_id = piwp.product_id
   -- Join condition to find overlapping ranges of running totals
   -- An order line (powp) consumes inventory (piwp) if their running total ranges overlap.
   -- powp.prev_running_ordered_qty is the start of the current order line's "demand range".
   -- powp.running_ordered_qty is the end of the current order line's "demand range".
   -- piwp.prev_running_inventory_qty is the start of the current inventory item's "supply range".
   -- piwp.running_inventory_qty is the end of the current inventory item's "supply range".
   AND powp.running_ordered_qty > piwp.prev_running_inventory_qty
   AND piwp.running_inventory_qty > powp.prev_running_ordered_qty
  GROUP BY
    powp.product_id,
    powp.product_name,
    powp.order_sequence,
    powp.ordered_qty
)
SELECT
  oa.product_name,
  -- Calculate the average pick percentage for each product
  -- (Total picked quantity / Total ordered quantity) * 100
  -- Handle division by zero if total ordered quantity is 0
  CASE
    WHEN SUM(oa.ordered_qty) = 0 THEN 0.0
    ELSE (SUM(oa.picked_qty_for_this_order_line) * 100.0 / SUM(oa.ordered_qty))
  END AS average_pick_percentage
FROM OrderAllocations AS oa
GROUP BY
  oa.product_name
ORDER BY
  oa.product_name