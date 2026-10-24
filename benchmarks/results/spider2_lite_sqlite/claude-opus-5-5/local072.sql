WITH jan AS (
  SELECT city_id, country_code_2, capital, date(insert_date) AS d
  FROM main.cities
  WHERE date(insert_date) BETWEEN '2022-01-01' AND '2022-01-31'
),
target AS (
  SELECT country_code_2
  FROM jan
  GROUP BY country_code_2
  HAVING COUNT(DISTINCT d) = 9
),
days AS (
  SELECT DISTINCT j.country_code_2, j.d
  FROM jan j
  JOIN target t ON j.country_code_2 = t.country_code_2
),
grp AS (
  SELECT country_code_2, d,
         julianday(d) - ROW_NUMBER() OVER (PARTITION BY country_code_2 ORDER BY d) AS g
  FROM days
),
streaks AS (
  SELECT country_code_2, g, MIN(d) AS start_date, MAX(d) AS end_date, COUNT(*) AS len
  FROM grp
  GROUP BY country_code_2, g
),
best AS (
  SELECT country_code_2, start_date, end_date, len,
         ROW_NUMBER() OVER (PARTITION BY country_code_2 ORDER BY len DESC, start_date) AS rn
  FROM streaks
)
SELECT b.country_code_2,
       (SELECT MIN(cc.country_name) FROM main.cities_countries cc WHERE cc.country_code_2 = b.country_code_2) AS country_name,
       b.start_date,
       b.end_date,
       b.len AS streak_days,
       SUM(CASE WHEN j.capital = 1 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS capital_proportion
FROM best b
JOIN jan j
  ON j.country_code_2 = b.country_code_2
 AND j.d BETWEEN b.start_date AND b.end_date
WHERE b.rn = 1
GROUP BY b.country_code_2, b.start_date, b.end_date, b.len