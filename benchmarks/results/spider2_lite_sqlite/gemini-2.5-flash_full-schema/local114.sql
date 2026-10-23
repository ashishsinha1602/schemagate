WITH SalesRepTotalSales AS (
    SELECT
        wsr.id AS sales_rep_id,
        wsr.name AS sales_rep_name,
        wsr.region_id,
        SUM(wo.total_amt_usd) AS sales_rep_total_sales
    FROM
        main.web_sales_reps AS wsr
    JOIN
        main.web_accounts AS wa
        ON wsr.id = wa.sales_rep_id
    JOIN
        main.web_orders AS wo
        ON wa.id = wo.account_id
    GROUP BY
        wsr.id, wsr.name, wsr.region_id
),
RegionAggregates AS (
    SELECT
        wr.id AS region_id,
        wr.name AS region_name,
        COUNT(wo.id) AS total_orders,
        SUM(wo.total_amt_usd) AS total_region_sales
    FROM
        main.web_region AS wr
    JOIN
        main.web_sales_reps AS wsr
        ON wr.id = wsr.region_id
    JOIN
        main.web_accounts AS wa
        ON wsr.id = wa.sales_rep_id
    JOIN
        main.web_orders AS wo
        ON wa.id = wo.account_id
    GROUP BY
        wr.id, wr.name
),
RankedSalesReps AS (
    SELECT
        sales_rep_id,
        sales_rep_name,
        region_id,
        sales_rep_total_sales,
        RANK() OVER (PARTITION BY region_id ORDER BY sales_rep_total_sales DESC) AS rnk
    FROM
        SalesRepTotalSales
)
SELECT
    ra.region_name,
    ra.total_orders,
    ra.total_region_sales,
    rsr.sales_rep_name,
    rsr.sales_rep_total_sales
FROM
    RegionAggregates AS ra
JOIN
    RankedSalesReps AS rsr
    ON ra.region_id = rsr.region_id
WHERE
    rsr.rnk = 1