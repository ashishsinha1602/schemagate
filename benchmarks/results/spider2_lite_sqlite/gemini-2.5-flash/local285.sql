WITH all_years_categories AS (
  SELECT DISTINCT SUBSTR(vwd.whsle_date, 1, 4) AS year, vc.category_name
  FROM main.veg_whsle_df AS vwd
  JOIN main.veg_cat AS vc
    ON vwd.item_code = vc.item_code
  WHERE
    SUBSTR(vwd.whsle_date, 1, 4) BETWEEN '2020' AND '2023'
  UNION
  SELECT DISTINCT SUBSTR(vtd.txn_date, 1, 4) AS year, vc.category_name
  FROM main.veg_txn_df AS vtd
  JOIN main.veg_cat AS vc
    ON vtd.item_code = vc.item_code
  WHERE
    SUBSTR(vtd.txn_date, 1, 4) BETWEEN '2020' AND '2023'
), whsle_agg AS (
  SELECT
    SUBSTR(vwd.whsle_date, 1, 4) AS year,
    vc.category_name,
    AVG(vwd."whsle_px_rmb-kg") AS avg_whsle_px,
    MAX(vwd."whsle_px_rmb-kg") AS max_whsle_px,
    MIN(vwd."whsle_px_rmb-kg") AS min_whsle_px,
    SUM(vwd."whsle_px_rmb-kg") AS total_whsle_px
  FROM main.veg_whsle_df AS vwd
  JOIN main.veg_cat AS vc
    ON vwd.item_code = vc.item_code
  WHERE
    SUBSTR(vwd.whsle_date, 1, 4) BETWEEN '2020' AND '2023'
  GROUP BY
    1,
    2
), txn_agg AS (
  SELECT
    SUBSTR(vtd.txn_date, 1, 4) AS year,
    vc.category_name,
    SUM(vtd."qty_sold(kg)" * vtd."unit_selling_px_rmb/kg") AS total_selling_px
  FROM main.veg_txn_df AS vtd
  JOIN main.veg_cat AS vc
    ON vtd.item_code = vc.item_code
  WHERE
    vtd."sale/return" = 'sale' AND SUBSTR(vtd.txn_date, 1, 4) BETWEEN '2020' AND '2023'
  GROUP BY
    1,
    2
), loss_agg AS (
  SELECT
    vc.category_name,
    AVG(vlrd."loss_rate_%") AS avg_loss_rate
  FROM main.veg_loss_rate_df AS vlrd
  JOIN main.veg_cat AS vc
    ON vlrd.item_code = vc.item_code
  GROUP BY
    1
)
SELECT
  ayc.year,
  ayc.category_name,
  ROUND(COALESCE(wa.avg_whsle_px, 0), 2) AS average_wholesale_price,
  ROUND(COALESCE(wa.max_whsle_px, 0), 2) AS maximum_wholesale_price,
  ROUND(COALESCE(wa.min_whsle_px, 0), 2) AS minimum_wholesale_price,
  ROUND(COALESCE(wa.max_whsle_px, 0) - COALESCE(wa.min_whsle_px, 0), 2) AS wholesale_price_difference,
  ROUND(COALESCE(wa.total_whsle_px, 0), 2) AS total_wholesale_price,
  ROUND(COALESCE(ta.total_selling_px, 0), 2) AS total_selling_price,
  ROUND(COALESCE(la.avg_loss_rate, 0), 2) AS average_loss_rate,
  ROUND(COALESCE(ta.total_selling_px, 0) * (COALESCE(la.avg_loss_rate, 0) / 100), 2) AS total_loss,
  ROUND(COALESCE(ta.total_selling_px, 0) - (COALESCE(ta.total_selling_px, 0) * (COALESCE(la.avg_loss_rate, 0) / 100)), 2) AS profit
FROM all_years_categories AS ayc
LEFT JOIN whsle_agg AS wa
  ON ayc.year = wa.year AND ayc.category_name = wa.category_name
LEFT JOIN txn_agg AS ta
  ON ayc.year = ta.year AND ayc.category_name = ta.category_name
LEFT JOIN loss_agg AS la
  ON ayc.category_name = la.category_name
ORDER BY
  ayc.year,
  ayc.category_name