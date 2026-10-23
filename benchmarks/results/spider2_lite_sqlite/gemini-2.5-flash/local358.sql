SELECT
  CASE
    WHEN T2.age >= 20 AND T2.age < 30 THEN '20s'
    WHEN T2.age >= 30 AND T2.age < 40 THEN '30s'
    WHEN T2.age >= 40 AND T2.age < 50 THEN '40s'
    WHEN T2.age >= 50 AND T2.age < 60 THEN '50s'
    ELSE 'Others'
  END AS age_category,
  COUNT(T2.user_id) AS user_count
FROM (
  SELECT
    user_id,
    CAST(strftime('%Y', 'now') AS INTEGER) - CAST(strftime('%Y', T1.birth_date) AS INTEGER) - (strftime('%m%d', 'now') < strftime('%m%d', T1.birth_date)) AS age
  FROM main.mst_users AS T1
  WHERE
    T1.birth_date IS NOT NULL AND T1.birth_date != ''
) AS T2
GROUP BY
  age_category
ORDER BY
  CASE age_category
    WHEN '20s' THEN 1
    WHEN '30s' THEN 2
    WHEN '40s' THEN 3
    WHEN '50s' THEN 4
    ELSE 5
  END