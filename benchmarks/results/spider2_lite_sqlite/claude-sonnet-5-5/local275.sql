WITH s AS (
  SELECT product_id, qty,
         (CAST(substr(mth,1,4) AS INTEGER) - 2016) * 12 + CAST(substr(mth,6,2) AS INTEGER) AS t
  FROM monthly_sales
  WHERE mth >= '2016-01'
),
cma AS (
  SELECT a.product_id, a.t, a.qty,
         (AVG(CASE WHEN b.t BETWEEN a.t-5 AND a.t+6 THEN b.qty END) +
          AVG(CASE WHEN b.t BETWEEN a.t-6 AND a.t+5 THEN b.qty END)) / 2.0 AS cma_val
  FROM s a
  JOIN s b ON a.product_id = b.product_id AND b.t BETWEEN a.t-6 AND a.t+6
  WHERE a.t BETWEEN 7 AND 30
  GROUP BY a.product_id, a.t, a.qty
)
SELECT p.id, p.name
FROM cma c
JOIN products p ON p.id = c.product_id
WHERE c.t BETWEEN 13 AND 24
GROUP BY p.id, p.name
HAVING COUNT(*) = 12
   AND SUM(CASE WHEN c.qty * 1.0 / c.cma_val > 2 THEN 1 ELSE 0 END) = 12