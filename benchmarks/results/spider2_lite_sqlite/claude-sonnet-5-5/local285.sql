WITH w AS (
  SELECT c.category_code, c.category_name, substr(s.whsle_date,1,4) AS yr,
         AVG(s."whsle_px_rmb-kg") AS avg_px,
         MAX(s."whsle_px_rmb-kg") AS max_px,
         MIN(s."whsle_px_rmb-kg") AS min_px,
         SUM(s."whsle_px_rmb-kg") AS total_px
  FROM veg_whsle_df s
  JOIN (SELECT DISTINCT item_code, category_code, category_name FROM veg_cat) c ON c.item_code = s.item_code
  WHERE substr(s.whsle_date,1,4) BETWEEN '2020' AND '2023'
  GROUP BY c.category_code, c.category_name, substr(s.whsle_date,1,4)
),
l AS (
  SELECT c.category_code, AVG(r."loss_rate_%") AS avg_loss_rate
  FROM veg_loss_rate_df r
  JOIN (SELECT DISTINCT item_code, category_code FROM veg_cat) c ON c.item_code = r.item_code
  GROUP BY c.category_code
),
t AS (
  SELECT c.category_code, substr(x.txn_date,1,4) AS yr,
         SUM(x."qty_sold(kg)" * x."unit_selling_px_rmb/kg") AS total_selling,
         SUM(x."qty_sold(kg)" * x."unit_selling_px_rmb/kg" * COALESCE(r."loss_rate_%",0) / 100.0) AS total_loss
  FROM veg_txn_df x
  JOIN (SELECT DISTINCT item_code, category_code FROM veg_cat) c ON c.item_code = x.item_code
  LEFT JOIN (SELECT item_code, AVG("loss_rate_%") AS "loss_rate_%" FROM veg_loss_rate_df GROUP BY item_code) r ON r.item_code = x.item_code
  WHERE x."sale/return" = 'sale'
    AND substr(x.txn_date,1,4) BETWEEN '2020' AND '2023'
  GROUP BY c.category_code, substr(x.txn_date,1,4)
)
SELECT w.yr AS year,
       w.category_name,
       ROUND(w.avg_px,2) AS avg_wholesale_price,
       ROUND(w.max_px,2) AS max_wholesale_price,
       ROUND(w.min_px,2) AS min_wholesale_price,
       ROUND(w.max_px - w.min_px,2) AS wholesale_price_difference,
       ROUND(w.total_px,2) AS total_wholesale_price,
       ROUND(COALESCE(t.total_selling,0),2) AS total_selling_price,
       ROUND(l.avg_loss_rate,2) AS avg_loss_rate,
       ROUND(COALESCE(t.total_loss,0),2) AS total_loss,
       ROUND(COALESCE(t.total_selling,0) - w.total_px - COALESCE(t.total_loss,0),2) AS profit
FROM w
LEFT JOIN t ON t.category_code = w.category_code AND t.yr = w.yr
LEFT JOIN l ON l.category_code = w.category_code
ORDER BY w.yr, w.category_name