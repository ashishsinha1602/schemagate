WITH daily AS (
  SELECT date(o.order_purchase_timestamp) AS d,
         COUNT(*) * 1.0 AS y,
         julianday(date(o.order_purchase_timestamp)) - julianday('2017-01-01') AS x
  FROM orders o
  JOIN order_items oi ON oi.order_id = o.order_id
  JOIN products p ON p.product_id = oi.product_id
  JOIN product_category_name_translation t ON t.product_category_name = p.product_category_name
  WHERE t.product_category_name_english = 'toys'
    AND date(o.order_purchase_timestamp) BETWEEN '2017-01-01' AND '2018-08-29'
  GROUP BY date(o.order_purchase_timestamp)
),
reg AS (
  SELECT COUNT(*) * 1.0 AS n, SUM(x) AS sx, SUM(y) AS sy, SUM(x * y) AS sxy, SUM(x * x) AS sxx
  FROM daily
),
slope AS (
  SELECT n, sx, sy, (n * sxy - sx * sy) / (n * sxx - sx * sx) AS b
  FROM reg
),
coef AS (
  SELECT b, (sy - b * sx) / n AS a
  FROM slope
),
days(d) AS (
  VALUES ('2018-12-03'), ('2018-12-04'), ('2018-12-05'), ('2018-12-06'),
         ('2018-12-07'), ('2018-12-08'), ('2018-12-09'), ('2018-12-10')
),
preds AS (
  SELECT days.d AS d,
         coef.a + coef.b * (julianday(days.d) - julianday('2017-01-01')) AS pred
  FROM days CROSS JOIN coef
),
ma AS (
  SELECT d,
         AVG(pred) OVER (ORDER BY d ROWS BETWEEN 2 PRECEDING AND 2 FOLLOWING) AS ma5
  FROM preds
)
SELECT SUM(ma5) AS sum_of_moving_averages
FROM ma
WHERE d BETWEEN '2018-12-05' AND '2018-12-08'