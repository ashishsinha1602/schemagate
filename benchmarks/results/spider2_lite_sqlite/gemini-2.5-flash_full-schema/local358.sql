SELECT
  CASE
    WHEN (2023 - CAST(SUBSTR(birth_date, 1, 4) AS INTEGER)) BETWEEN 20 AND 29 THEN '20s'
    WHEN (2023 - CAST(SUBSTR(birth_date, 1, 4) AS INTEGER)) BETWEEN 30 AND 39 THEN '30s'
    WHEN (2023 - CAST(SUBSTR(birth_date, 1, 4) AS INTEGER)) BETWEEN 40 AND 49 THEN '40s'
    WHEN (2023 - CAST(SUBSTR(birth_date, 1, 4) AS INTEGER)) BETWEEN 50 AND 59 THEN '50s'
    ELSE 'Others'
  END AS age_category,
  COUNT(user_id) AS user_count
FROM main.mst_users
WHERE birth_date IS NOT NULL
GROUP BY 1
ORDER BY
  CASE
    WHEN age_category = '20s' THEN 1
    WHEN age_category = '30s' THEN 2
    WHEN age_category = '40s' THEN 3
    WHEN age_category = '50s' THEN 4
    ELSE 5
  END