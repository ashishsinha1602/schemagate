WITH TeamWins AS (
  SELECT
    T.team_long_name AS team_name,
    CASE
      WHEN M.home_team_goal > M.away_team_goal THEN 1
      ELSE 0
    END AS home_win,
    CASE
      WHEN M.away_team_goal > M.home_team_goal THEN 1
      ELSE 0
    END AS away_win
  FROM main.Match AS M
  JOIN main.Team AS T
    ON M.home_team_api_id = T.team_api_id
  UNION ALL
  SELECT
    T.team_long_name AS team_name,
    CASE
      WHEN M.home_team_goal > M.away_team_goal THEN 0
      ELSE 0
    END AS home_win,
    CASE
      WHEN M.away_team_goal > M.home_team_goal THEN 1
      ELSE 0
    END AS away_win
  FROM main.Match AS M
  JOIN main.Team AS T
    ON M.away_team_api_id = T.team_api_id
)
SELECT
  team_name,
  SUM(home_win + away_win) AS total_wins
FROM TeamWins
GROUP BY
  team_name
ORDER BY
  total_wins DESC
LIMIT 10