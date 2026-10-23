SELECT
  T1.name_given,
  T2.g AS score,
  'Games Played' AS statistic
FROM main.player AS T1
INNER JOIN main.batting AS T2
  ON T1.player_id = T2.player_id
WHERE
  T2.g = (
    SELECT
      MAX(g)
    FROM main.batting
  )
UNION ALL
SELECT
  T1.name_given,
  T2.r AS score,
  'Runs' AS statistic
FROM main.player AS T1
INNER JOIN main.batting AS T2
  ON T1.player_id = T2.player_id
WHERE
  T2.r = (
    SELECT
      MAX(r)
    FROM main.batting
  )
UNION ALL
SELECT
  T1.name_given,
  T2.h AS score,
  'Hits' AS statistic
FROM main.player AS T1
INNER JOIN main.batting AS T2
  ON T1.player_id = T2.player_id
WHERE
  T2.h = (
    SELECT
      MAX(h)
    FROM main.batting
  )
UNION ALL
SELECT
  T1.name_given,
  T2.hr AS score,
  'Home Runs' AS statistic
FROM main.player AS T1
INNER JOIN main.batting AS T2
  ON T1.player_id = T2.player_id
WHERE
  T2.hr = (
    SELECT
      MAX(hr)
    FROM main.batting
  )