WITH RECURSIVE MonthlyInventoryCalc AS (
    -- Base Case: Inventory at the end of December 2018, which serves as the starting inventory for January 2019.
    SELECT
        it.product_id,
        '2018-12' AS mth, -- This represents the month whose *ending* inventory we are carrying forward.
        it.qty AS ending_inventory_after_restock, -- This is the inventory at the end of Dec 2018.
        pm.qty_minimum,
        pm.qty_purchase
    FROM main.inventory_totals AS it
    JOIN main.product_minimums AS pm
        ON it.product_id = pm.product_id

    UNION ALL

    -- Recursive Step: Calculate inventory for the next month.
    SELECT
        mic.product_id,
        -- Calculate the next month string (e.g., '2018-12' -> '2019-01', '2019-01' -> '2019-02').
        CASE SUBSTR(mic.mth, 6, 2)
            WHEN '12' THEN (CAST(SUBSTR(mic.mth, 1, 4) AS INTEGER) + 1) || '-01'
            ELSE SUBSTR(mic.mth, 1, 4) || '-' || PRINTF('%02d', CAST(SUBSTR(mic.mth, 6, 2) AS INTEGER) + 1)
        END AS next_mth,
        -- Calculate the ending inventory for the next month after sales and potential restocking.
        CASE
            -- If inventory drops below minimum after sales, restock by qty_purchase.
            WHEN (mic.ending_inventory_after_restock - COALESCE(ms.qty, 0)) < mic.qty_minimum
            THEN (mic.ending_inventory_after_restock - COALESCE(ms.qty, 0)) + mic.qty_purchase
            -- Otherwise, just subtract sales.
            ELSE (mic.ending_inventory_after_restock - COALESCE(ms.qty, 0))
        END AS ending_inventory_for_next_mth,
        mic.qty_minimum,
        mic.qty_purchase
    FROM MonthlyInventoryCalc AS mic
    LEFT JOIN main.monthly_sales AS ms
        ON mic.product_id = ms.product_id
        AND (
            -- Join with sales for the *next* month.
            CASE SUBSTR(mic.mth, 6, 2)
                WHEN '12' THEN (CAST(SUBSTR(mic.mth, 1, 4) AS INTEGER) + 1) || '-01'
                ELSE SUBSTR(mic.mth, 1, 4) || '-' || PRINTF('%02d', CAST(SUBSTR(mic.mth, 6, 2) AS INTEGER) + 1)
            END
        ) = ms.mth
    -- Continue recursion until we have calculated the ending inventory for December 2019.
    WHERE mic.mth < '2019-12'
),
MonthlyResults AS (
    -- Select only the results for 2019 and calculate the absolute difference.
    SELECT
        product_id,
        mth,
        ABS(ending_inventory_after_restock - qty_minimum) AS abs_diff
    FROM MonthlyInventoryCalc
    WHERE mth LIKE '2019-%' -- Filter for all months in 2019.
),
RankedResults AS (
    -- Rank each month's result for each product by the absolute difference.
    SELECT
        product_id,
        mth,
        abs_diff,
        ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY abs_diff ASC, mth ASC) as rn
    FROM MonthlyResults
)
-- Select the month with the smallest absolute difference for each product.
SELECT
    product_id,
    mth,
    abs_diff
FROM RankedResults
WHERE rn = 1