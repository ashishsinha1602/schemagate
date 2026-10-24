WITH totals AS (
  SELECT player_id,
         SUM(g) AS games_played,
         SUM(r) AS runs,
         SUM(h) AS hits,
         SUM(hr) AS home_runs
  FROM main.batting
  GROUP BY player_id
),
best AS (
  SELECT 'games_played' AS metric, player_id, games_played AS score
  FROM totals
  WHERE games_played = (SELECT MAX(games_played) FROM totals)
  UNION ALL
  SELECT 'runs', player_id, runs
  FROM totals
  WHERE runs = (SELECT MAX(runs) FROM totals)
  UNION ALL
  SELECT 'hits', player_id, hits
  FROM totals
  WHERE hits = (SELECT MAX(hits) FROM totals)
  UNION ALL
  SELECT 'home_runs', player_id, home_runs
  FROM totals
  WHERE home_runs = (SELECT MAX(home_runs) FROM totals)
)
SELECT b.metric, p.name_given, b.score
FROM best b
JOIN main.player p ON p.player_id = b.player_id