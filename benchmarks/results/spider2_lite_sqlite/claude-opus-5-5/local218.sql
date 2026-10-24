WITH team_goals AS (
  SELECT home_team_api_id AS team_id, season, home_team_goal AS goals FROM Match
  UNION ALL
  SELECT away_team_api_id AS team_id, season, away_team_goal AS goals FROM Match
),
season_totals AS (
  SELECT team_id, season, SUM(goals) AS total_goals
  FROM team_goals
  GROUP BY team_id, season
),
team_max AS (
  SELECT team_id, MAX(total_goals) AS max_goals
  FROM season_totals
  GROUP BY team_id
),
ordered AS (
  SELECT max_goals,
         ROW_NUMBER() OVER (ORDER BY max_goals) AS rn,
         COUNT(*) OVER () AS cnt
  FROM team_max
)
SELECT AVG(max_goals) AS median_highest_season_goals
FROM ordered
WHERE rn IN ((cnt + 1) / 2, (cnt + 2) / 2)