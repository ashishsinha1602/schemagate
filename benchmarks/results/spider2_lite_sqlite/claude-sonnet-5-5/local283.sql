WITH results AS (
  SELECT m.season, m.league_id, m.country_id, m.home_team_api_id AS team_api_id,
         CASE WHEN m.home_team_goal > m.away_team_goal THEN 3
              WHEN m.home_team_goal = m.away_team_goal THEN 1 ELSE 0 END AS pts
  FROM Match m
  UNION ALL
  SELECT m.season, m.league_id, m.country_id, m.away_team_api_id,
         CASE WHEN m.away_team_goal > m.home_team_goal THEN 3
              WHEN m.home_team_goal = m.away_team_goal THEN 1 ELSE 0 END
  FROM Match m
),
totals AS (
  SELECT season, league_id, country_id, team_api_id, SUM(pts) AS total_points
  FROM results
  GROUP BY season, league_id, country_id, team_api_id
),
ranked AS (
  SELECT t.*, ROW_NUMBER() OVER (PARTITION BY season, league_id ORDER BY total_points DESC, team_api_id) AS rn
  FROM totals t
)
SELECT r.season, tm.team_long_name AS champion_team, l.name AS league, c.name AS country, r.total_points
FROM ranked r
JOIN Team tm ON tm.team_api_id = r.team_api_id
JOIN League l ON l.id = r.league_id
JOIN Country c ON c.id = r.country_id
WHERE r.rn = 1
ORDER BY r.season, c.name, l.name