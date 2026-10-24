WITH team_results AS (
  SELECT season, league_id, country_id, home_team_api_id AS team_api_id,
         CASE WHEN home_team_goal > away_team_goal THEN 3
              WHEN home_team_goal = away_team_goal THEN 1 ELSE 0 END AS pts
  FROM Match
  UNION ALL
  SELECT season, league_id, country_id, away_team_api_id AS team_api_id,
         CASE WHEN away_team_goal > home_team_goal THEN 3
              WHEN away_team_goal = home_team_goal THEN 1 ELSE 0 END AS pts
  FROM Match
),
totals AS (
  SELECT season, league_id, country_id, team_api_id, SUM(pts) AS total_points
  FROM team_results
  GROUP BY season, league_id, country_id, team_api_id
),
ranked AS (
  SELECT t.*,
         RANK() OVER (PARTITION BY season, league_id ORDER BY total_points DESC) AS rnk
  FROM totals t
)
SELECT r.season,
       tm.team_long_name AS team_name,
       l.name AS league,
       c.name AS country,
       r.total_points
FROM ranked r
JOIN Team tm ON tm.team_api_id = r.team_api_id
JOIN League l ON l.id = r.league_id
JOIN Country c ON c.id = r.country_id
WHERE r.rnk = 1
ORDER BY r.season, l.name