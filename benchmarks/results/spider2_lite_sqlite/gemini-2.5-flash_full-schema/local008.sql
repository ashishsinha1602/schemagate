WITH PlayerCareerStats AS (
  SELECT
    player_id,
    SUM(g) AS total_g,
    SUM(r) AS total_r,
    SUM(h) AS total_h,
    SUM(hr) AS total_hr
  FROM main.batting
  GROUP BY
    player_id
), MaxStats AS (
  SELECT
    MAX(total_g) AS max_g,
    MAX(total_r) AS max_r,
    MAX(total_h) AS max_h,
    MAX(total_hr) AS max_hr
  FROM PlayerCareerStats
)
SELECT
  T1.name_given,
  'Games Played' AS stat_category,
  T2.total_g AS stat_value
FROM main.player AS T1
JOIN PlayerCareerStats AS T2
  ON T1.player_id = T2.player_id
JOIN MaxStats AS T3
  ON T2.total_g = T3.max_g
UNION ALL
SELECT
  T1.name_given,
  'Runs' AS stat_category,
  T2.total_r AS stat_value
FROM main.player AS T1
JOIN PlayerCareerStats AS T2
  ON T1.player_id = T2.player_id
JOIN MaxStats AS T3
  ON T2.total_r = T3.max_r
UNION ALL
SELECT
  T1.name_given,
  'Hits' AS stat_category,
  T2.total_h AS stat_value
FROM main.player AS T1
JOIN PlayerCareerStats AS T2
  ON T1.player_id = T2.player_id
JOIN MaxStats AS T3
  ON T2.total_h = T3.max_h
UNION ALL
SELECT
  T1.name_given,
  'Home Runs' AS stat_category,
  T2.total_hr AS stat_value
FROM main.player AS T1
JOIN PlayerCareerStats AS T2
  ON T1.player_id = T2.player_id
JOIN MaxStats AS T3
  ON T2.total_hr = T3.max_hr