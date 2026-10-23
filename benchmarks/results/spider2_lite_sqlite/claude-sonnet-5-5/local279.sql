WITH RECURSIVE s AS (
  SELECT product_id, mth, qty,
         ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY mth) AS rn
  FROM monthly_sales
  WHERE mth >= '2019-01' AND mth < '2020'
),
rec(product_id, mth, rn, ending) AS (
  SELECT s.product_id, s.mth, s.rn,
         CASE WHEN it.qty - s.qty < pm.qty_minimum
              THEN it.qty - s.qty + pm.qty_purchase
              ELSE it.qty - s.qty END
  FROM s
  JOIN inventory_totals it ON it.product_id = s.product_id
  JOIN product_minimums pm ON pm.product_id = s.product_id
  WHERE s.rn = 1
  UNION ALL
  SELECT s.product_id, s.mth, s.rn,
         CASE WHEN r.ending - s.qty < pm.qty_minimum
              THEN r.ending - s.qty + pm.qty_purchase
              ELSE r.ending - s.qty END
  FROM rec r
  JOIN s ON s.product_id = r.product_id AND s.rn = r.rn + 1
  JOIN product_minimums pm ON pm.product_id = s.product_id
),
diffs AS (
  SELECT r.product_id, r.mth, ABS(r.ending - pm.qty_minimum) AS diff,
         ROW_NUMBER() OVER (PARTITION BY r.product_id ORDER BY ABS(r.ending - pm.qty_minimum), r.mth) AS k
  FROM rec r
  JOIN product_minimums pm ON pm.product_id = r.product_id
)
SELECT product_id, mth, diff
FROM diffs
WHERE k = 1
ORDER BY product_id