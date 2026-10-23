WITH pm AS (
SELECT home_player_1 AS pid, CASE WHEN home_team_goal > away_team_goal THEN 1 ELSE 0 END AS won FROM Match WHERE home_player_1 IS NOT NULL AND home_team_goal <> away_team_goal
UNION ALL SELECT home_player_2, CASE WHEN home_team_goal > away_team_goal THEN 1 ELSE 0 END FROM Match WHERE home_player_2 IS NOT NULL AND home_team_goal <> away_team_goal
UNION ALL SELECT home_player_3, CASE WHEN home_team_goal > away_team_goal THEN 1 ELSE 0 END FROM Match WHERE home_player_3 IS NOT NULL AND home_team_goal <> away_team_goal
UNION ALL SELECT home_player_4, CASE WHEN home_team_goal > away_team_goal THEN 1 ELSE 0 END FROM Match WHERE home_player_4 IS NOT NULL AND home_team_goal <> away_team_goal
UNION ALL SELECT home_player_5, CASE WHEN home_team_goal > away_team_goal THEN 1 ELSE 0 END FROM Match WHERE home_player_5 IS NOT NULL AND home_team_goal <> away_team_goal
UNION ALL SELECT home_player_6, CASE WHEN home_team_goal > away_team_goal THEN 1 ELSE 0 END FROM Match WHERE home_player_6 IS NOT NULL AND home_team_goal <> away_team_goal
UNION ALL SELECT home_player_7, CASE WHEN home_team_goal > away_team_goal THEN 1 ELSE 0 END FROM Match WHERE home_player_7 IS NOT NULL AND home_team_goal <> away_team_goal
UNION ALL SELECT home_player_8, CASE WHEN home_team_goal > away_team_goal THEN 1 ELSE 0 END FROM Match WHERE home_player_8 IS NOT NULL AND home_team_goal <> away_team_goal
UNION ALL SELECT home_player_9, CASE WHEN home_team_goal > away_team_goal THEN 1 ELSE 0 END FROM Match WHERE home_player_9 IS NOT NULL AND home_team_goal <> away_team_goal
UNION ALL SELECT home_player_10, CASE WHEN home_team_goal > away_team_goal THEN 1 ELSE 0 END FROM Match WHERE home_player_10 IS NOT NULL AND home_team_goal <> away_team_goal
UNION ALL SELECT home_player_11, CASE WHEN home_team_goal > away_team_goal THEN 1 ELSE 0 END FROM Match WHERE home_player_11 IS NOT NULL AND home_team_goal <> away_team_goal
UNION ALL SELECT away_player_1, CASE WHEN away_team_goal > home_team_goal THEN 1 ELSE 0 END FROM Match WHERE away_player_1 IS NOT NULL AND home_team_goal <> away_team_goal
UNION ALL SELECT away_player_2, CASE WHEN away_team_goal > home_team_goal THEN 1 ELSE 0 END FROM Match WHERE away_player_2 IS NOT NULL AND home_team_goal <> away_team_goal
UNION ALL SELECT away_player_3, CASE WHEN away_team_goal > home_team_goal THEN 1 ELSE 0 END FROM Match WHERE away_player_3 IS NOT NULL AND home_team_goal <> away_team_goal
UNION ALL SELECT away_player_4, CASE WHEN away_team_goal > home_team_goal THEN 1 ELSE 0 END FROM Match WHERE away_player_4 IS NOT NULL AND home_team_goal <> away_team_goal
UNION ALL SELECT away_player_5, CASE WHEN away_team_goal > home_team_goal THEN 1 ELSE 0 END FROM Match WHERE away_player_5 IS NOT NULL AND home_team_goal <> away_team_goal
UNION ALL SELECT away_player_6, CASE WHEN away_team_goal > home_team_goal THEN 1 ELSE 0 END FROM Match WHERE away_player_6 IS NOT NULL AND home_team_goal <> away_team_goal
UNION ALL SELECT away_player_7, CASE WHEN away_team_goal > home_team_goal THEN 1 ELSE 0 END FROM Match WHERE away_player_7 IS NOT NULL AND home_team_goal <> away_team_goal
UNION ALL SELECT away_player_8, CASE WHEN away_team_goal > home_team_goal THEN 1 ELSE 0 END FROM Match WHERE away_player_8 IS NOT NULL AND home_team_goal <> away_team_goal
UNION ALL SELECT away_player_9, CASE WHEN away_team_goal > home_team_goal THEN 1 ELSE 0 END FROM Match WHERE away_player_9 IS NOT NULL AND home_team_goal <> away_team_goal
UNION ALL SELECT away_player_10, CASE WHEN away_team_goal > home_team_goal THEN 1 ELSE 0 END FROM Match WHERE away_player_10 IS NOT NULL AND home_team_goal <> away_team_goal
UNION ALL SELECT away_player_11, CASE WHEN away_team_goal > home_team_goal THEN 1 ELSE 0 END FROM Match WHERE away_player_11 IS NOT NULL AND home_team_goal <> away_team_goal
),
stats AS (
SELECT pid, SUM(won) AS wins, SUM(1 - won) AS losses
FROM pm
GROUP BY pid
)
SELECT category, player_name, matches FROM (
SELECT 'most_wins' AS category, p.player_name AS player_name, s.wins AS matches
FROM stats s JOIN Player p ON p.player_api_id = s.pid
ORDER BY s.wins DESC, p.player_name
LIMIT 1
)
UNION ALL
SELECT category, player_name, matches FROM (
SELECT 'most_losses' AS category, p.player_name AS player_name, s.losses AS matches
FROM stats s JOIN Player p ON p.player_api_id = s.pid
ORDER BY s.losses DESC, p.player_name
LIMIT 1
)