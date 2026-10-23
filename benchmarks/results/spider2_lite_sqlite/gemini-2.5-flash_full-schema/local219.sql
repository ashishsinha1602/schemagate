WITH TeamWins AS (
    -- Calculate wins for home teams
    SELECT
        M.league_id,
        M.home_team_api_id AS team_api_id,
        CASE WHEN M.home_team_goal > M.away_team_goal THEN 1 ELSE 0 END AS win_count
    FROM main.Match AS M
    UNION ALL
    -- Calculate wins for away teams
    SELECT
        M.league_id,
        M.away_team_api_id AS team_api_id,
        CASE WHEN M.away_team_goal > M.home_team_goal THEN 1 ELSE 0 END AS win_count
    FROM main.Match AS M
),
TotalTeamWinsPerLeague AS (
    -- Sum total wins for each team in each league
    SELECT
        TW.league_id,
        TW.team_api_id,
        SUM(TW.win_count) AS total_wins
    FROM TeamWins AS TW
    GROUP BY
        TW.league_id,
        TW.team_api_id
),
RankedTeamWins AS (
    -- Rank teams within each league by their total wins, picking one in case of a tie
    SELECT
        TTW.league_id,
        TTW.team_api_id,
        TTW.total_wins,
        ROW_NUMBER() OVER (PARTITION BY TTW.league_id ORDER BY TTW.total_wins ASC) AS rn
    FROM TotalTeamWinsPerLeague AS TTW
)
SELECT
    L.name AS league_name,
    T.team_long_name AS team_name,
    RTW.total_wins
FROM RankedTeamWins AS RTW
JOIN main.League AS L
    ON RTW.league_id = L.id
JOIN main.Team AS T
    ON RTW.team_api_id = T.team_api_id
WHERE
    RTW.rn = 1