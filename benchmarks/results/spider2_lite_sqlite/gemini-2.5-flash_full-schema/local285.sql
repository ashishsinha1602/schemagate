WITH TransactionData AS (
    SELECT
        strftime('%Y', t.txn_date) AS sales_year,
        c.category_name,
        t.item_code,
        t."qty_sold(kg)" AS qty_sold_kg,
        t."unit_selling_px_rmb/kg" AS unit_selling_px,
        t.txn_date
    FROM main.veg_txn_df AS t
    JOIN main.veg_cat AS c
        ON t.item_code = c.item_code
    WHERE
        t."sale/return" = 'sale'
        AND strftime('%Y', t.txn_date) BETWEEN '2020' AND '2023'
),
SalesWithWholesale AS (
    SELECT
        td.sales_year,
        td.category_name,
        td.item_code,
        td.qty_sold_kg,
        td.unit_selling_px,
        w."whsle_px_rmb-kg" AS whsle_px
    FROM TransactionData AS td
    LEFT JOIN main.veg_whsle_df AS w
        ON td.item_code = w.item_code AND td.txn_date = w.whsle_date
    WHERE w."whsle_px_rmb-kg" IS NOT NULL -- Exclude transactions where wholesale price is unknown
),
FinalSalesData AS (
    SELECT
        sw.sales_year,
        sw.category_name,
        sw.item_code,
        sw.qty_sold_kg,
        sw.unit_selling_px,
        sw.whsle_px,
        COALESCE(lr."loss_rate_%", 0.0) AS loss_rate_percent -- Assume 0% loss if no specific rate is found
    FROM SalesWithWholesale AS sw
    LEFT JOIN main.veg_loss_rate_df AS lr
        ON sw.item_code = lr.item_code
)
SELECT
    fsd.sales_year,
    fsd.category_name,
    ROUND(AVG(fsd.whsle_px), 2) AS average_wholesale_price,
    ROUND(MAX(fsd.whsle_px), 2) AS maximum_wholesale_price,
    ROUND(MIN(fsd.whsle_px), 2) AS minimum_wholesale_price,
    ROUND(MAX(fsd.whsle_px) - MIN(fsd.whsle_px), 2) AS wholesale_price_difference,
    ROUND(SUM(fsd.qty_sold_kg * fsd.whsle_px), 2) AS total_wholesale_price,
    ROUND(SUM(fsd.qty_sold_kg * fsd.unit_selling_px), 2) AS total_selling_price,
    ROUND(AVG(fsd.loss_rate_percent), 2) AS average_loss_rate,
    ROUND(SUM(fsd.qty_sold_kg * fsd.whsle_px * (fsd.loss_rate_percent / 100.0)), 2) AS total_loss,
    ROUND(SUM(fsd.qty_sold_kg * fsd.unit_selling_px) - SUM(fsd.qty_sold_kg * fsd.whsle_px * (1 + fsd.loss_rate_percent / 100.0)), 2) AS profit
FROM FinalSalesData AS fsd
GROUP BY
    fsd.sales_year,
    fsd.category_name
ORDER BY
    fsd.sales_year,
    fsd.category_name