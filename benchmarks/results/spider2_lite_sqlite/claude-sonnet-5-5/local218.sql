WITH g AS (
  SELECT home_team_api_id AS team, season, home_team_goal AS goals FROM Match
  UNION ALL
  SELECT away_team_api_id AS team, season, away_team_goal AS goals FROM Match
),
s AS (
  SELECT team, season, SUM(goals) AS total
  FROM g
  GROUP BY team, season
),
m AS (
  SELECT team, MAX(total) AS best
  FROM s
  GROUP BY team
),
r AS (
  SELECT best, ROW_NUMBER() OVER (ORDER BY best) AS rn, COUNT(*) OVER () AS cnt
  FROM m
)
SELECT AVG(best) AS median_highest_season_goals
FROM r
WHERE rn IN ((cnt + 1) / 2, (cnt + 2) / 2)