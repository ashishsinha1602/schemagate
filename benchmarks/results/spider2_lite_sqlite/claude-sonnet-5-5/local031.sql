WITH m AS (
  SELECT substr(order_purchase_timestamp,1,4) AS yr,
         substr(order_purchase_timestamp,1,7) AS ym,
         COUNT(*) AS cnt
  FROM olist_orders
  WHERE order_status = 'delivered'
    AND substr(order_purchase_timestamp,1,4) IN ('2016','2017','2018')
  GROUP BY yr, ym
),
y AS (
  SELECT yr, SUM(cnt) AS total
  FROM m
  GROUP BY yr
)
SELECT MAX(m.cnt) AS highest_monthly_delivered_orders
FROM m
WHERE m.yr = (SELECT yr FROM y ORDER BY total ASC LIMIT 1)