WITH TeamWins AS (
  SELECT
    T.team_long_name,
    SUM(CASE
      WHEN M.home_team_api_id = T.team_api_id AND M.home_team_goal > M.away_team_goal THEN 1
      WHEN M.away_team_api_id = T.team_api_id AND M.away_team_goal > M.home_team_goal THEN 1
      ELSE 0
    END) AS total_wins
  FROM main.Team AS T
  JOIN main.Match AS M
    ON T.team_api_id = M.home_team_api_id
    OR T.team_api_id = M.away_team_api_id
  GROUP BY
    T.team_long_name
)
SELECT
  team_long_name
FROM TeamWins
ORDER BY
  total_wins DESC
LIMIT 10