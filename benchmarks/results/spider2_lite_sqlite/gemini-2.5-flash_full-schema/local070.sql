WITH FilteredCities AS (
  SELECT
    insert_date,
    city_name,
    city_id
  FROM main.cities
  WHERE
    country_code_2 = 'cn' AND strftime('%Y-%m', insert_date) = '2021-07'
), DistinctDatesWithCity AS (
  SELECT
    insert_date,
    city_name
  FROM (
    SELECT
      insert_date,
      city_name,
      ROW_NUMBER() OVER (PARTITION BY insert_date ORDER BY city_id) AS rn_city
    FROM FilteredCities
  )
  WHERE
    rn_city = 1
), RankedDates AS (
  SELECT
    insert_date,
    city_name,
    CAST(strftime('%J', insert_date) AS INTEGER) - ROW_NUMBER() OVER (ORDER BY insert_date) AS group_id
  FROM DistinctDatesWithCity
), StreakLengths AS (
  SELECT
    group_id,
    COUNT(insert_date) AS streak_length
  FROM RankedDates
  GROUP BY
    group_id
), MinMaxLengths AS (
  SELECT
    MIN(streak_length) AS min_len,
    MAX(streak_length) AS max_len
  FROM StreakLengths
)
SELECT
  T1.insert_date,
  UPPER(SUBSTR(T1.city_name, 1, 1)) || LOWER(SUBSTR(T1.city_name, 2)) AS city_name
FROM RankedDates AS T1
JOIN StreakLengths AS T2
  ON T1.group_id = T2.group_id
JOIN MinMaxLengths AS T3
WHERE
  T2.streak_length = T3.min_len OR T2.streak_length = T3.max_len
ORDER BY
  T1.insert_date