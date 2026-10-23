WITH results AS (
  SELECT home_team_api_id AS team_api_id,
         CASE WHEN home_team_goal > away_team_goal THEN 1 ELSE 0 END AS win
  FROM Match
  UNION ALL
  SELECT away_team_api_id AS team_api_id,
         CASE WHEN away_team_goal > home_team_goal THEN 1 ELSE 0 END AS win
  FROM Match
)
SELECT t.team_long_name, SUM(r.win) AS wins
FROM results r
JOIN Team t ON t.team_api_id = r.team_api_id
GROUP BY t.team_api_id, t.team_long_name
ORDER BY wins DESC
LIMIT 10