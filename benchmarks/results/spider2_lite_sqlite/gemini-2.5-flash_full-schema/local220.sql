WITH PlayerMatchOutcomes AS (
    -- Home team players and their match outcomes
    SELECT
        M.home_player_1 AS player_id,
        CASE WHEN M.home_team_goal > M.away_team_goal THEN 'win' WHEN M.home_team_goal < M.away_team_goal THEN 'loss' ELSE 'draw' END AS outcome
    FROM main.Match AS M WHERE M.home_player_1 IS NOT NULL
    UNION ALL
    SELECT M.home_player_2 AS player_id, CASE WHEN M.home_team_goal > M.away_team_goal THEN 'win' WHEN M.home_team_goal < M.away_team_goal THEN 'loss' ELSE 'draw' END FROM main.Match AS M WHERE M.home_player_2 IS NOT NULL
    UNION ALL
    SELECT M.home_player_3 AS player_id, CASE WHEN M.home_team_goal > M.away_team_goal THEN 'win' WHEN M.home_team_goal < M.away_team_goal THEN 'loss' ELSE 'draw' END FROM main.Match AS M WHERE M.home_player_3 IS NOT NULL
    UNION ALL
    SELECT M.home_player_4 AS player_id, CASE WHEN M.home_team_goal > M.away_team_goal THEN 'win' WHEN M.home_team_goal < M.away_team_goal THEN 'loss' ELSE 'draw' END FROM main.Match AS M WHERE M.home_player_4 IS NOT NULL
    UNION ALL
    SELECT M.home_player_5 AS player_id, CASE WHEN M.home_team_goal > M.away_team_goal THEN 'win' WHEN M.home_team_goal < M.away_team_goal THEN 'loss' ELSE 'draw' END FROM main.Match AS M WHERE M.home_player_5 IS NOT NULL
    UNION ALL
    SELECT M.home_player_6 AS player_id, CASE WHEN M.home_team_goal > M.away_team_goal THEN 'win' WHEN M.home_team_goal < M.away_team_goal THEN 'loss' ELSE 'draw' END FROM main.Match AS M WHERE M.home_player_6 IS NOT NULL
    UNION ALL
    SELECT M.home_player_7 AS player_id, CASE WHEN M.home_team_goal > M.away_team_goal THEN 'win' WHEN M.home_team_goal < M.away_team_goal THEN 'loss' ELSE 'draw' END FROM main.Match AS M WHERE M.home_player_7 IS NOT NULL
    UNION ALL
    SELECT M.home_player_8 AS player_id, CASE WHEN M.home_team_goal > M.away_team_goal THEN 'win' WHEN M.home_team_goal < M.away_team_goal THEN 'loss' ELSE 'draw' END FROM main.Match AS M WHERE M.home_player_8 IS NOT NULL
    UNION ALL
    SELECT M.home_player_9 AS player_id, CASE WHEN M.home_team_goal > M.away_team_goal THEN 'win' WHEN M.home_team_goal < M.away_team_goal THEN 'loss' ELSE 'draw' END FROM main.Match AS M WHERE M.home_player_9 IS NOT NULL
    UNION ALL
    SELECT M.home_player_10 AS player_id, CASE WHEN M.home_team_goal > M.away_team_goal THEN 'win' WHEN M.home_team_goal < M.away_team_goal THEN 'loss' ELSE 'draw' END FROM main.Match AS M WHERE M.home_player_10 IS NOT NULL
    UNION ALL
    SELECT M.home_player_11 AS player_id, CASE WHEN M.home_team_goal > M.away_team_goal THEN 'win' WHEN M.home_team_goal < M.away_team_goal THEN 'loss' ELSE 'draw' END FROM main.Match AS M WHERE M.home_player_11 IS NOT NULL

    UNION ALL

    -- Away team players and their match outcomes
    SELECT
        M.away_player_1 AS player_id,
        CASE WHEN M.away_team_goal > M.home_team_goal THEN 'win' WHEN M.away_team_goal < M.home_team_goal THEN 'loss' ELSE 'draw' END AS outcome
    FROM main.Match AS M WHERE M.away_player_1 IS NOT NULL
    UNION ALL
    SELECT M.away_player_2 AS player_id, CASE WHEN M.away_team_goal > M.home_team_goal THEN 'win' WHEN M.away_team_goal < M.home_team_goal THEN 'loss' ELSE 'draw' END FROM main.Match AS M WHERE M.away_player_2 IS NOT NULL
    UNION ALL
    SELECT M.away_player_3 AS player_id, CASE WHEN M.away_team_goal > M.home_team_goal THEN 'win' WHEN M.away_team_goal < M.home_team_goal THEN 'loss' ELSE 'draw' END FROM main.Match AS M WHERE M.away_player_3 IS NOT NULL
    UNION ALL
    SELECT M.away_player_4 AS player_id, CASE WHEN M.away_team_goal > M.home_team_goal THEN 'win' WHEN M.away_team_goal < M.home_team_goal THEN 'loss' ELSE 'draw' END FROM main.Match AS M WHERE M.away_player_4 IS NOT NULL
    UNION ALL
    SELECT M.away_player_5 AS player_id, CASE WHEN M.away_team_goal > M.home_team_goal THEN 'win' WHEN M.away_team_goal < M.home_team_goal THEN 'loss' ELSE 'draw' END FROM main.Match AS M WHERE M.away_player_5 IS NOT NULL
    UNION ALL
    SELECT M.away_player_6 AS player_id, CASE WHEN M.away_team_goal > M.home_team_goal THEN 'win' WHEN M.away_team_goal < M.home_team_goal THEN 'loss' ELSE 'draw' END FROM main.Match AS M WHERE M.away_player_6 IS NOT NULL
    UNION ALL
    SELECT M.away_player_7 AS player_id, CASE WHEN M.away_team_goal > M.home_team_goal THEN 'win' WHEN M.away_team_goal < M.home_team_goal THEN 'loss' ELSE 'draw' END FROM main.Match AS M WHERE M.away_player_7 IS NOT NULL
    UNION ALL
    SELECT M.away_player_8 AS player_id, CASE WHEN M.away_team_goal > M.home_team_goal THEN 'win' WHEN M.away_team_goal < M.home_team_goal THEN 'loss' ELSE 'draw' END FROM main.Match AS M WHERE M.away_player_8 IS NOT NULL
    UNION ALL
    SELECT M.away_player_9 AS player_id, CASE WHEN M.away_team_goal > M.home_team_goal THEN 'win' WHEN M.away_team_goal < M.home_team_goal THEN 'loss' ELSE 'draw' END FROM main.Match AS M WHERE M.away_player_9 IS NOT NULL
    UNION ALL
    SELECT M.away_player_10 AS player_id, CASE WHEN M.away_team_goal > M.home_team_goal THEN 'win' WHEN M.away_team_goal < M.home_team_goal THEN 'loss' ELSE 'draw' END FROM main.Match AS M WHERE M.away_player_10 IS NOT NULL
    UNION ALL
    SELECT M.away_player_11 AS player_id, CASE WHEN M.away_team_goal > M.home_team_goal THEN 'win' WHEN M.away_team_goal < M.home_team_goal THEN 'loss' ELSE 'draw' END FROM main.Match AS M WHERE M.away_player_11 IS NOT NULL
),
PlayerStats AS (
    SELECT
        player_id,
        SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) AS wins,
        SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) AS losses
    FROM PlayerMatchOutcomes
    WHERE outcome != 'draw' -- Exclude draws as per requirement
    GROUP BY player_id
),
MaxWins AS (
    SELECT
        player_id,
        wins
    FROM PlayerStats
    ORDER BY wins DESC
    LIMIT 1
),
MaxLosses AS (
    SELECT
        player_id,
        losses
    FROM PlayerStats
    ORDER BY losses DESC
    LIMIT 1
)
SELECT
    P.player_name,
    MW.wins AS total_matches,
    'Highest Wins' AS category
FROM MaxWins AS MW
JOIN main.Player AS P ON MW.player_id = P.id

UNION ALL

SELECT
    P.player_name,
    ML.losses AS total_matches,
    'Highest Losses' AS category
FROM MaxLosses AS ML
JOIN main.Player AS P ON ML.player_id = P.id