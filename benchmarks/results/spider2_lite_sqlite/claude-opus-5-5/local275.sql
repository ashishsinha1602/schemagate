WITH ms AS (
  SELECT product_id,
         mth,
         qty,
         ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY mth) AS ts
  FROM monthly_sales
  WHERE mth >= '2016-01-01'
),
cma AS (
  SELECT product_id,
         mth,
         qty,
         ts,
         (AVG(qty) OVER (PARTITION BY product_id ORDER BY ts ROWS BETWEEN 5 PRECEDING AND 6 FOLLOWING)
        + AVG(qty) OVER (PARTITION BY product_id ORDER BY ts ROWS BETWEEN 6 PRECEDING AND 5 FOLLOWING)) / 2.0 AS cma
  FROM ms
)
SELECT p.id AS product_id,
       p.name AS product_name
FROM cma c
JOIN products p ON p.id = c.product_id
WHERE c.ts BETWEEN 7 AND 30
  AND substr(c.mth, 1, 4) = '2017'
GROUP BY p.id, p.name
HAVING MIN(c.qty * 1.0 / NULLIF(c.cma, 0)) > 2
   AND COUNT(*) = 12