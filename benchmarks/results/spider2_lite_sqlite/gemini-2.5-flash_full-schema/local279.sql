WITH RECURSIVE MonthlyInventory AS (
    -- Anchor member: December 2018 inventory levels
    SELECT
        it.product_id,
        '2018-12' AS mth,
        it.qty AS ending_inventory, -- This is the starting inventory for January 2019
        pm.qty_minimum,
        pm.qty_purchase
    FROM
        main.inventory_totals AS it
    JOIN
        main.product_minimums AS pm
        ON it.product_id = pm.product_id

    UNION ALL

    -- Recursive member: Calculate inventory for subsequent months in 2019
    SELECT
        mi.product_id,
        STRFTIME('%Y-%m', DATE(mi.mth || '-01', '+1 month')) AS mth,
        CASE
            -- If ending inventory before restock is below minimum, restock by qty_purchase
            WHEN (mi.ending_inventory - COALESCE(ms.qty, 0)) < mi.qty_minimum
            THEN (mi.ending_inventory - COALESCE(ms.qty, 0)) + mi.qty_purchase
            -- Otherwise, no restock
            ELSE (mi.ending_inventory - COALESCE(ms.qty, 0))
        END AS ending_inventory,
        mi.qty_minimum,
        mi.qty_purchase
    FROM
        MonthlyInventory AS mi
    LEFT JOIN
        main.monthly_sales AS ms
        ON mi.product_id = ms.product_id AND STRFTIME('%Y-%m', DATE(mi.mth || '-01', '+1 month')) = ms.mth
    WHERE
        mi.mth < '2019-12' -- Continue recursion until December 2019 inventory is calculated
),
RankedDifferences AS (
    -- Calculate the absolute difference for each product for each month in 2019
    -- and rank them to find the smallest difference
    SELECT
        mi.product_id,
        mi.mth,
        ABS(mi.ending_inventory - mi.qty_minimum) AS absolute_difference,
        ROW_NUMBER() OVER (PARTITION BY mi.product_id ORDER BY ABS(mi.ending_inventory - mi.qty_minimum) ASC, mi.mth ASC) AS rn
    FROM
        MonthlyInventory AS mi
    WHERE
        mi.mth LIKE '2019-%' -- Filter for months in 2019
)
-- Select the product_id, month, and absolute difference for the smallest difference
SELECT
    rd.product_id,
    rd.mth,
    rd.absolute_difference
FROM
    RankedDifferences AS rd
WHERE
    rd.rn = 1