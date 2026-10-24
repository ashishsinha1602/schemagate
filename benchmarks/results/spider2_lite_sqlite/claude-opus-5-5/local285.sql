WITH txn AS (
  SELECT
    item_code,
    SUBSTR(txn_date, 1, 10) AS d,
    CAST(SUBSTR(txn_date, 1, 4) AS INTEGER) AS yr,
    COUNT(*) AS cnt,
    SUM("qty_sold(kg)") AS qty,
    SUM("qty_sold(kg)" * "unit_selling_px_rmb/kg") AS sell_amt
  FROM veg_txn_df
  WHERE CAST(SUBSTR(txn_date, 1, 4) AS INTEGER) BETWEEN 2020 AND 2023
  GROUP BY item_code, SUBSTR(txn_date, 1, 10)
),
whs AS (
  SELECT
    item_code,
    SUBSTR(whsle_date, 1, 10) AS d,
    "whsle_px_rmb-kg" AS whsle_px
  FROM veg_whsle_df
  WHERE CAST(SUBSTR(whsle_date, 1, 4) AS INTEGER) BETWEEN 2020 AND 2023
),
joined AS (
  SELECT
    t.yr,
    c.category_name,
    w.whsle_px,
    t.cnt,
    t.qty,
    t.sell_amt,
    l."loss_rate_%" AS loss_rate
  FROM txn t
  JOIN whs w
    ON w.item_code = t.item_code
   AND w.d = t.d
  JOIN veg_cat c
    ON c.item_code = t.item_code
  JOIN veg_loss_rate_df l
    ON l.item_code = t.item_code
),
agg AS (
  SELECT
    yr,
    category_name,
    SUM(whsle_px * cnt) * 1.0 / SUM(cnt) AS avg_whsle,
    MAX(whsle_px) AS max_whsle,
    MIN(whsle_px) AS min_whsle,
    SUM(whsle_px * qty) AS total_whsle,
    SUM(sell_amt) AS total_sell,
    SUM(loss_rate * cnt) * 1.0 / SUM(cnt) AS avg_loss_rate,
    SUM(whsle_px * qty * loss_rate / 100.0) AS total_loss
  FROM joined
  GROUP BY yr, category_name
)
SELECT
  yr AS year,
  category_name,
  ROUND(avg_whsle, 2) AS avg_wholesale_price,
  ROUND(max_whsle, 2) AS max_wholesale_price,
  ROUND(min_whsle, 2) AS min_wholesale_price,
  ROUND(max_whsle - min_whsle, 2) AS wholesale_price_difference,
  ROUND(total_whsle, 2) AS total_wholesale_price,
  ROUND(total_sell, 2) AS total_selling_price,
  ROUND(avg_loss_rate, 2) AS avg_loss_rate,
  ROUND(total_loss, 2) AS total_loss,
  ROUND(total_sell - total_whsle - total_loss, 2) AS profit
FROM agg
ORDER BY year, category_name