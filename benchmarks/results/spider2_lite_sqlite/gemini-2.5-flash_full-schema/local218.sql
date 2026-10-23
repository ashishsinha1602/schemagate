WITH TeamSeasonGoals AS (
    SELECT
        T.team_long_name AS team_name,
        M.season,
        SUM(M.home_team_goal) AS total_goals
    FROM Match AS M
    JOIN Team AS T
        ON M.home_team_api_id = T.team_api_id
    GROUP BY
        T.team_long_name,
        M.season

    UNION ALL

    SELECT
        T.team_long_name AS team_name,
        M.season,
        SUM(M.away_team_goal) AS total_goals
    FROM Match AS M
    JOIN Team AS T
        ON M.away_team_api_id = T.team_api_id
    GROUP BY
        T.team_long_name,
        M.season
),
TeamHighestSeasonGoals AS (
    SELECT
        team_name,
        MAX(total_goals) AS highest_season_goals
    FROM TeamSeasonGoals
    GROUP BY
        team_name
),
RankedGoals AS (
    SELECT
        highest_season_goals,
        ROW_NUMBER() OVER (ORDER BY highest_season_goals) AS rn,
        COUNT(*) OVER () AS total_count
    FROM TeamHighestSeasonGoals
)
SELECT
    AVG(highest_season_goals)
FROM RankedGoals
WHERE
    rn IN ((total_count + 1) / 2, (total_count + 2) / 2)