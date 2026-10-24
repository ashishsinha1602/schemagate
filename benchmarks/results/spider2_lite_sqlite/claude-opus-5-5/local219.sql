WITH team_league AS (
  SELECT league_id, home_team_api_id AS team_api_id FROM Match
  UNION
  SELECT league_id, away_team_api_id FROM Match
),
wins AS (
  SELECT league_id,
         CASE WHEN home_team_goal > away_team_goal THEN home_team_api_id
              WHEN away_team_goal > home_team_goal THEN away_team_api_id END AS team_api_id
  FROM Match
  WHERE home_team_goal <> away_team_goal
),
win_counts AS (
  SELECT tl.league_id, tl.team_api_id, COUNT(w.team_api_id) AS total_wins
  FROM team_league tl
  LEFT JOIN wins w ON w.league_id = tl.league_id AND w.team_api_id = tl.team_api_id
  GROUP BY tl.league_id, tl.team_api_id
),
ranked AS (
  SELECT wc.*, ROW_NUMBER() OVER (PARTITION BY wc.league_id ORDER BY wc.total_wins ASC, wc.team_api_id ASC) AS rn
  FROM win_counts wc
)
SELECT l.name AS league, t.team_long_name AS team, r.total_wins
FROM ranked r
JOIN League l ON l.id = r.league_id
LEFT JOIN Team t ON t.team_api_id = r.team_api_id
WHERE r.rn = 1
ORDER BY l.name