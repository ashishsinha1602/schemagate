WITH TeamMatchPoints AS (
    -- Calculate points for home teams
    SELECT
        M.season,
        M.league_id,
        M.country_id,
        M.home_team_api_id AS team_api_id,
        CASE
            WHEN M.home_team_goal > M.away_team_goal THEN 3
            WHEN M.home_team_goal = M.away_team_goal THEN 1
            ELSE 0
        END AS points
    FROM main.Match AS M
    UNION ALL
    -- Calculate points for away teams
    SELECT
        M.season,
        M.league_id,
        M.country_id,
        M.away_team_api_id AS team_api_id,
        CASE
            WHEN M.away_team_goal > M.home_team_goal THEN 3
            WHEN M.away_team_goal = M.home_team_goal THEN 1
            ELSE 0
        END AS points
    FROM main.Match AS M
),
TeamSeasonPoints AS (
    -- Aggregate total points for each team per season and league
    SELECT
        TMP.season,
        TMP.league_id,
        TMP.country_id,
        TMP.team_api_id,
        SUM(TMP.points) AS total_points
    FROM TeamMatchPoints AS TMP
    GROUP BY
        TMP.season,
        TMP.league_id,
        TMP.country_id,
        TMP.team_api_id
),
RankedTeams AS (
    -- Rank teams within each season and league by their total points
    SELECT
        TSP.season,
        TSP.league_id,
        TSP.country_id,
        TSP.team_api_id,
        TSP.total_points,
        RANK() OVER (PARTITION BY TSP.season, TSP.league_id ORDER BY TSP.total_points DESC) AS rnk
    FROM TeamSeasonPoints AS TSP
)
SELECT
    T.team_long_name AS champion_team_name,
    L.name AS league_name,
    C.name AS country_name,
    RT.total_points
FROM RankedTeams AS RT
JOIN main.Team AS T
    ON RT.team_api_id = T.team_api_id
JOIN main.League AS L
    ON RT.league_id = L.id
JOIN main.Country AS C
    ON RT.country_id = C.id
WHERE RT.rnk = 1
ORDER BY
    C.name,
    L.name,
    RT.season