WITH pos(n) AS (
  VALUES (1),(2),(3),(4),(5),(6),(7),(8),(9),(10),(11)
),
apps AS (
  SELECT
    CASE p.n
      WHEN 1 THEN m.home_player_1 WHEN 2 THEN m.home_player_2 WHEN 3 THEN m.home_player_3
      WHEN 4 THEN m.home_player_4 WHEN 5 THEN m.home_player_5 WHEN 6 THEN m.home_player_6
      WHEN 7 THEN m.home_player_7 WHEN 8 THEN m.home_player_8 WHEN 9 THEN m.home_player_9
      WHEN 10 THEN m.home_player_10 WHEN 11 THEN m.home_player_11
    END AS player_id,
    CASE WHEN m.home_team_goal > m.away_team_goal THEN 'win' ELSE 'loss' END AS result
  FROM Match m CROSS JOIN pos p
  WHERE m.home_team_goal <> m.away_team_goal
  UNION ALL
  SELECT
    CASE p.n
      WHEN 1 THEN m.away_player_1 WHEN 2 THEN m.away_player_2 WHEN 3 THEN m.away_player_3
      WHEN 4 THEN m.away_player_4 WHEN 5 THEN m.away_player_5 WHEN 6 THEN m.away_player_6
      WHEN 7 THEN m.away_player_7 WHEN 8 THEN m.away_player_8 WHEN 9 THEN m.away_player_9
      WHEN 10 THEN m.away_player_10 WHEN 11 THEN m.away_player_11
    END AS player_id,
    CASE WHEN m.away_team_goal > m.home_team_goal THEN 'win' ELSE 'loss' END AS result
  FROM Match m CROSS JOIN pos p
  WHERE m.home_team_goal <> m.away_team_goal
),
counts AS (
  SELECT player_id,
         SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) AS wins,
         SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) AS losses
  FROM apps
  WHERE player_id IS NOT NULL
  GROUP BY player_id
)
SELECT * FROM (
  SELECT 'most wins' AS category, pl.player_name, c.wins AS match_count
  FROM counts c JOIN Player pl ON pl.player_api_id = c.player_id
  ORDER BY c.wins DESC LIMIT 1
)
UNION ALL
SELECT * FROM (
  SELECT 'most losses' AS category, pl.player_name, c.losses AS match_count
  FROM counts c JOIN Player pl ON pl.player_api_id = c.player_id
  ORDER BY c.losses DESC LIMIT 1
)