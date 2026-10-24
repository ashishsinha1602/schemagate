WITH ages AS (
  SELECT
    user_id,
    (CAST(strftime('%Y%m%d', 'now') AS INTEGER) - CAST(REPLACE(SUBSTR(birth_date, 1, 10), '-', '') AS INTEGER)) / 10000 AS age
  FROM main.mst_users
),
cats AS (
  SELECT
    user_id,
    CASE
      WHEN age BETWEEN 20 AND 29 THEN '20s'
      WHEN age BETWEEN 30 AND 39 THEN '30s'
      WHEN age BETWEEN 40 AND 49 THEN '40s'
      WHEN age BETWEEN 50 AND 59 THEN '50s'
      ELSE 'others'
    END AS age_category
  FROM ages
)
SELECT age_category, COUNT(DISTINCT user_id) AS user_count
FROM cats
GROUP BY age_category
ORDER BY age_category