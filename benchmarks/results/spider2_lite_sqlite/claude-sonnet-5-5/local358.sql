WITH u AS (
  SELECT user_id,
         (CAST(strftime('%Y%m%d','now') AS INTEGER) - CAST(replace(birth_date,'-','') AS INTEGER)) / 10000 AS age
  FROM mst_users
)
SELECT CASE
         WHEN age BETWEEN 20 AND 29 THEN '20s'
         WHEN age BETWEEN 30 AND 39 THEN '30s'
         WHEN age BETWEEN 40 AND 49 THEN '40s'
         WHEN age BETWEEN 50 AND 59 THEN '50s'
         ELSE 'others'
       END AS age_category,
       COUNT(*) AS user_count
FROM u
GROUP BY age_category