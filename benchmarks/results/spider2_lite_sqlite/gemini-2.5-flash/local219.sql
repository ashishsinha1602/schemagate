WITH HomeWins AS (
    SELECT
        M.league_id,
        L.name AS league_name,
        M.home_team_api_id AS team_api_id,
        T.team_long_name,
        1 AS win_count
    FROM main.Match AS M
    JOIN main.League AS L ON M.league_id = L.id
    JOIN main.Team AS T ON M.home_team_api_id = T.team_api_id
    WHERE M.home_team_goal > M.away_team_goal
), AwayWins AS (
    SELECT
        M.league_id,
        L.name AS league_name,
        M.away_team_api_id AS team_api_id,
        T.team_long_name,
        1 AS win_count
    FROM main.Match AS M
    JOIN main.League AS L ON M.league_id = L.id
    JOIN main.Team AS T ON M.away_team_api_id = T.team_api_id
    WHERE M.away_team_goal > M.home_team_goal
), AllWins AS (
    SELECT league_id, league_name, team_api_id, team_long_name, win_count FROM HomeWins
    UNION ALL
    SELECT league_id, league_name, team_api_id, team_long_name, win_count FROM AwayWins
), AllTeamsInLeagues AS (
    SELECT DISTINCT
        L.id AS league_id,
        L.name AS league_name,
        T.team_api_id,
        T.team_long_name
    FROM main.Match AS M
    JOIN main.League AS L ON M.league_id = L.id
    JOIN main.Team AS T ON M.home_team_api_id = T.team_api_id
    UNION
    SELECT DISTINCT
        L.id AS league_id,
        L.name AS league_name,
        T.team_api_id,
        T.team_long_name
    FROM main.Match AS M
    JOIN main.League AS L ON M.league_id = L.id
    JOIN main.Team AS T ON M.away_team_api_id = T.team_api_id
), TeamTotalWins AS (
    SELECT
        ATL.league_name,
        ATL.team_long_name,
        COALESCE(SUM(AW.win_count), 0) AS total_wins
    FROM AllTeamsInLeagues AS ATL
    LEFT JOIN AllWins AS AW
        ON ATL.league_id = AW.league_id
        AND ATL.team_api_id = AW.team_api_id
    GROUP BY ATL.league_id, ATL.league_name, ATL.team_api_id, ATL.team_long_name
)
SELECT
    league_name,
    team_long_name,
    total_wins
FROM (
    SELECT
        league_name,
        team_long_name,
        total_wins,
        ROW_NUMBER() OVER (PARTITION BY league_name ORDER BY total_wins ASC, team_long_name ASC) as rn
    FROM TeamTotalWins
)
WHERE rn = 1