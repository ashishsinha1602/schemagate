WITH daily AS (
  SELECT date(o.order_purchase_timestamp) AS d,
         SUM(oi.price) AS s
  FROM order_items oi
  JOIN orders o ON o.order_id = oi.order_id
  JOIN products p ON p.product_id = oi.product_id
  JOIN product_category_name_translation t ON t.product_category_name = p.product_category_name
  WHERE t.product_category_name_english = 'toys'
    AND date(o.order_purchase_timestamp) BETWEEN '2017-01-01' AND '2018-08-29'
  GROUP BY date(o.order_purchase_timestamp)
),
pts AS (
  SELECT julianday(d) - julianday('2017-01-01') AS x,
         s AS y
  FROM daily
),
reg AS (
  SELECT (COUNT(*) * SUM(x * y) - SUM(x) * SUM(y)) * 1.0
           / (COUNT(*) * SUM(x * x) - SUM(x) * SUM(x)) AS b,
         AVG(x) AS mx,
         AVG(y) AS my
  FROM pts
),
coef AS (
  SELECT b, my - b * mx AS a
  FROM reg
),
days(d) AS (
  SELECT '2018-12-03'
  UNION ALL
  SELECT date(d, '+1 day') FROM days WHERE d < '2018-12-10'
),
pred AS (
  SELECT days.d,
         coef.a + coef.b * (julianday(days.d) - julianday('2017-01-01')) AS p
  FROM days
  CROSS JOIN coef
),
ma AS (
  SELECT d,
         AVG(p) OVER (ORDER BY d ROWS BETWEEN 2 PRECEDING AND 2 FOLLOWING) AS mavg
  FROM pred
)
SELECT SUM(mavg) AS sum_moving_averages
FROM ma
WHERE d BETWEEN '2018-12-05' AND '2018-12-08'