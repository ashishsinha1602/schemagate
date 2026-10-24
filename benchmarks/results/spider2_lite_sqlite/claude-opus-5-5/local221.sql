SELECT t.team_long_name, COUNT(*) AS wins
FROM (
  SELECT home_team_api_id AS team_api_id FROM Match WHERE home_team_goal > away_team_goal
  UNION ALL
  SELECT away_team_api_id AS team_api_id FROM Match WHERE away_team_goal > home_team_goal
) w
JOIN Team t ON t.team_api_id = w.team_api_id
GROUP BY t.team_api_id, t.team_long_name
ORDER BY wins DESC
LIMIT 10