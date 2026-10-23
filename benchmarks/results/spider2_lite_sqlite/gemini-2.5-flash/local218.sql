WITH TeamSeasonGoals AS (
  SELECT
    team_id,
    season,
    SUM(goals) AS total_season_goals
  FROM (
    SELECT
      home_team_api_id AS team_id,
      season,
      home_team_goal AS goals
    FROM main.Match
    UNION ALL
    SELECT
      away_team_api_id AS team_id,
      season,
      away_team_goal AS goals
    FROM main.Match
  ) AS all_goals
  GROUP BY
    team_id,
    season
), MaxSeasonGoalsPerTeam AS (
  SELECT
    team_id,
    MAX(total_season_goals) AS highest_season_goals
  FROM TeamSeasonGoals
  GROUP BY
    team_id
), SortedGoals AS (
  SELECT
    highest_season_goals,
    ROW_NUMBER() OVER (ORDER BY highest_season_goals) AS rn,
    COUNT(*) OVER () AS total_rows
  FROM MaxSeasonGoalsPerTeam
)
SELECT
  AVG(highest_season_goals * 1.0)
FROM SortedGoals
WHERE
  rn = (total_rows + 1) / 2 OR rn = (total_rows + 2) / 2