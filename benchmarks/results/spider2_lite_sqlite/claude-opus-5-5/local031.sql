WITH delivered AS (
  SELECT order_id,
         strftime('%Y', order_delivered_customer_date) AS yr,
         strftime('%m', order_delivered_customer_date) AS mon
  FROM main.olist_orders
  WHERE order_status = 'delivered'
    AND order_delivered_customer_date IS NOT NULL
    AND strftime('%Y', order_delivered_customer_date) IN ('2016', '2017', '2018')
),
annual AS (
  SELECT yr, COUNT(*) AS cnt
  FROM delivered
  GROUP BY yr
  ORDER BY cnt ASC
  LIMIT 1
),
monthly AS (
  SELECT d.mon, COUNT(*) AS cnt
  FROM delivered d
  JOIN annual a ON d.yr = a.yr
  GROUP BY d.mon
)
SELECT MAX(cnt) AS highest_monthly_delivered_orders
FROM monthly