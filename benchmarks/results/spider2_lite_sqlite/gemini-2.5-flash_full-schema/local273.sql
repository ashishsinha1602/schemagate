WITH OrderedInventory AS (
    SELECT
        i.product_id,
        i.qty AS inventory_qty,
        p.purchased,
        i.id AS inventory_item_id, -- Added for stable sort in case of ties in purchased date and qty
        ROW_NUMBER() OVER (PARTITION BY i.product_id ORDER BY p.purchased ASC, i.qty ASC, i.id ASC) AS inv_rank
    FROM
        main.inventory AS i
    JOIN
        main.purchases AS p ON i.purchase_id = p.id
),
CumulativeInventory AS (
    SELECT
        product_id,
        SUM(inventory_qty) OVER (PARTITION BY product_id ORDER BY inv_rank) AS cumulative_inv_qty
    FROM
        OrderedInventory
),
TotalAvailableInventory AS (
    SELECT
        product_id,
        MAX(cumulative_inv_qty) AS total_available_qty
    FROM
        CumulativeInventory
    GROUP BY
        product_id
),
OrderedPickingLines AS (
    SELECT
        pl.product_id,
        pl.qty AS requested_qty,
        pl.order_id,
        pl.line_no,
        ROW_NUMBER() OVER (PARTITION BY pl.product_id ORDER BY pl.order_id ASC, pl.line_no ASC) AS pick_rank
    FROM
        main.picking_line AS pl
),
CumulativePickingLines AS (
    SELECT
        product_id,
        requested_qty,
        pick_rank,
        SUM(requested_qty) OVER (PARTITION BY product_id ORDER BY pick_rank) AS cumulative_req_qty,
        COALESCE(SUM(requested_qty) OVER (PARTITION BY product_id ORDER BY pick_rank ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS prev_cumulative_req_qty
    FROM
        OrderedPickingLines
)
SELECT
    p.name AS product_name,
    (SUM(
        MAX(0,
            MIN(cpl.cumulative_req_qty, COALESCE(tai.total_available_qty, 0)) - cpl.prev_cumulative_req_qty
        )
    ) * 100.0 / SUM(cpl.requested_qty)) AS average_pick_percentage
FROM
    CumulativePickingLines AS cpl
JOIN
    main.products AS p ON cpl.product_id = p.id
LEFT JOIN
    TotalAvailableInventory AS tai ON cpl.product_id = tai.product_id
GROUP BY
    p.name
ORDER BY
    p.name