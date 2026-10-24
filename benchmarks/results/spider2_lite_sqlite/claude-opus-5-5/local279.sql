WITH RECURSIVE sales AS (
  SELECT ms.product_id,
         ms.mth,
         ms.qty,
         ROW_NUMBER() OVER (PARTITION BY ms.product_id ORDER BY ms.mth) AS rn
  FROM monthly_sales ms
  WHERE strftime('%Y', ms.mth) = '2019'
),
rec AS (
  SELECT it.product_id,
         '2018-12-01' AS mth,
         0 AS rn,
         CAST(it.qty AS REAL) AS inv
  FROM inventory_totals it
  JOIN product_minimums pm ON pm.product_id = it.product_id
  UNION ALL
  SELECT r.product_id,
         s.mth,
         s.rn,
         CASE
           WHEN r.inv - s.qty < pm.qty_minimum THEN r.inv - s.qty + pm.qty_purchase
           ELSE r.inv - s.qty
         END
  FROM rec r
  JOIN sales s ON s.product_id = r.product_id AND s.rn = r.rn + 1
  JOIN product_minimums pm ON pm.product_id = r.product_id
),
diffs AS (
  SELECT r.product_id,
         r.mth,
         ABS(r.inv - pm.qty_minimum) AS abs_diff,
         ROW_NUMBER() OVER (
           PARTITION BY r.product_id
           ORDER BY ABS(r.inv - pm.qty_minimum), r.mth
         ) AS rk
  FROM rec r
  JOIN product_minimums pm ON pm.product_id = r.product_id
  WHERE r.rn >= 1
)
SELECT product_id, mth, abs_diff
FROM diffs
WHERE rk = 1
ORDER BY product_id