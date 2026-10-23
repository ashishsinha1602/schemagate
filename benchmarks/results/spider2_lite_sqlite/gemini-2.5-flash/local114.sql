WITH sales_rep_performance AS (
    SELECT
        wsr.id AS sales_rep_id,
        wsr.name AS sales_rep_name,
        wsr.region_id,
        SUM(wo.total_amt_usd) AS rep_total_sales
    FROM main.web_sales_reps AS wsr
    JOIN main.web_accounts AS wa
        ON wsr.id = wa.sales_rep_id
    JOIN main.web_orders AS wo
        ON wa.id = wo.account_id
    GROUP BY
        wsr.id,
        wsr.name,
        wsr.region_id
),
region_overall_summary AS (
    SELECT
        wr.id AS region_id,
        wr.name AS region_name,
        COUNT(wo.id) AS total_orders,
        SUM(wo.total_amt_usd) AS region_total_sales
    FROM main.web_region AS wr
    JOIN main.web_sales_reps AS wsr
        ON wr.id = wsr.region_id
    JOIN main.web_accounts AS wa
        ON wsr.id = wa.sales_rep_id
    JOIN main.web_orders AS wo
        ON wa.id = wo.account_id
    GROUP BY
        wr.id,
        wr.name
),
max_sales_per_region AS (
    SELECT
        srp.region_id,
        MAX(srp.rep_total_sales) AS max_rep_sales_in_region
    FROM sales_rep_performance AS srp
    GROUP BY
        srp.region_id
)
SELECT
    ros.region_name,
    ros.total_orders,
    ros.region_total_sales,
    GROUP_CONCAT(srp.sales_rep_name || ' (' || srp.rep_total_sales || ')', '; ') AS top_sales_reps_and_sales
FROM region_overall_summary AS ros
JOIN max_sales_per_region AS mspr
    ON ros.region_id = mspr.region_id
JOIN sales_rep_performance AS srp
    ON mspr.region_id = srp.region_id AND mspr.max_rep_sales_in_region = srp.rep_total_sales
GROUP BY
    ros.region_name,
    ros.total_orders,
    ros.region_total_sales
ORDER BY
    ros.region_name