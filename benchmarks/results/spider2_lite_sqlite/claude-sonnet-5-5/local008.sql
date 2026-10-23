WITH t AS (
  SELECT player_id, SUM(g) AS g, SUM(r) AS r, SUM(h) AS h, SUM(hr) AS hr
  FROM batting
  GROUP BY player_id
)
SELECT p.name_given, 'games played' AS stat, t.g AS value
FROM t JOIN player p ON p.player_id = t.player_id
WHERE t.g = (SELECT MAX(g) FROM t)
UNION ALL
SELECT p.name_given, 'runs' AS stat, t.r AS value
FROM t JOIN player p ON p.player_id = t.player_id
WHERE t.r = (SELECT MAX(r) FROM t)
UNION ALL
SELECT p.name_given, 'hits' AS stat, t.h AS value
FROM t JOIN player p ON p.player_id = t.player_id
WHERE t.h = (SELECT MAX(h) FROM t)
UNION ALL
SELECT p.name_given, 'home runs' AS stat, t.hr AS value
FROM t JOIN player p ON p.player_id = t.player_id
WHERE t.hr = (SELECT MAX(hr) FROM t)