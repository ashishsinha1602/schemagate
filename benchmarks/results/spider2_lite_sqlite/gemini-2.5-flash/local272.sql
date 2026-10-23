WITH OrderNeeds AS (
    SELECT
        product_id,
        SUM(qty) AS needed_qty
    FROM main.orderlines
    WHERE order_id = 423
    GROUP BY product_id
),
InventoryWithRunningSum AS (
    SELECT
        product_id,
        aisle,
        position,
        qty AS available_qty,
        purchased,
        SUM(qty) OVER (PARTITION BY product_id ORDER BY purchased ASC, qty ASC) AS running_available_qty
    FROM main.inventory_with_dims
    WHERE warehouse = 1
),
AvailableInventory AS (
    SELECT
        product_id,
        aisle,
        position,
        available_qty,
        purchased,
        running_available_qty,
        LAG(running_available_qty, 1, 0) OVER (PARTITION BY product_id ORDER BY purchased ASC, available_qty ASC) AS prev_running_available_qty
    FROM InventoryWithRunningSum
)
SELECT
    ai.product_id,
    ai.aisle,
    ai.position,
    CASE
        -- If the needed quantity has already been fulfilled by previous inventory lots
        WHEN ai.prev_running_available_qty >= ord_needs.needed_qty THEN 0
        -- If the current inventory lot (and previous ones) are entirely needed
        WHEN ai.running_available_qty <= ord_needs.needed_qty THEN ai.available_qty
        -- Otherwise, pick only the remaining quantity needed from this lot
        ELSE ord_needs.needed_qty - ai.prev_running_available_qty
    END AS picked_qty
FROM OrderNeeds AS ord_needs
JOIN AvailableInventory AS ai
    ON ord_needs.product_id = ai.product_id
WHERE
    -- Only include rows where a positive quantity is picked
    CASE
        WHEN ai.prev_running_available_qty >= ord_needs.needed_qty THEN 0
        WHEN ai.running_available_qty <= ord_needs.needed_qty THEN ai.available_qty
        ELSE ord_needs.needed_qty - ai.prev_running_available_qty
    END > 0
ORDER BY
    ai.product_id,
    ai.purchased ASC,
    ai.available_qty ASC