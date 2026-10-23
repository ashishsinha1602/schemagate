WITH tm AS (
  SELECT league_id, home_team_api_id AS team_api_id,
         CASE WHEN home_team_goal > away_team_goal THEN 1 ELSE 0 END AS w
  FROM Match
  UNION ALL
  SELECT league_id, away_team_api_id AS team_api_id,
         CASE WHEN away_team_goal > home_team_goal THEN 1 ELSE 0 END AS w
  FROM Match
), agg AS (
  SELECT league_id, team_api_id, SUM(w) AS wins
  FROM tm
  GROUP BY league_id, team_api_id
), ranked AS (
  SELECT league_id, team_api_id, wins,
         ROW_NUMBER() OVER (PARTITION BY league_id ORDER BY wins ASC, team_api_id ASC) AS rn
  FROM agg
)
SELECT l.name AS league, t.team_long_name AS team, r.wins
FROM ranked r
JOIN League l ON l.id = r.league_id
JOIN Team t ON t.team_api_id = r.team_api_id
WHERE r.rn = 1