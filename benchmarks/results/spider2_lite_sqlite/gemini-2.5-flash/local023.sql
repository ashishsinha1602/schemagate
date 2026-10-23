WITH PlayerTotalRuns AS (
    SELECT
        bb.striker AS player_id,
        SUM(bs.runs_scored) AS total_runs
    FROM main.ball_by_ball AS bb
    JOIN main.batsman_scored AS bs
        ON bb.match_id = bs.match_id
        AND bb.over_id = bs.over_id
        AND bb.ball_id = bs.ball_id
        AND bb.innings_no = bs.innings_no
    JOIN main.match AS m
        ON bb.match_id = m.match_id
    WHERE m.season_id = 5
    GROUP BY
        bb.striker
),
PlayerMatchCounts AS (
    SELECT
        pm.player_id,
        COUNT(DISTINCT pm.match_id) AS matches_played
    FROM main.player_match AS pm
    JOIN main.match AS m
        ON pm.match_id = m.match_id
    WHERE m.season_id = 5
    GROUP BY
        pm.player_id
)
SELECT
    p.player_name,
    CAST(ptr.total_runs AS REAL) / pmc.matches_played AS batting_average
FROM PlayerTotalRuns AS ptr
JOIN PlayerMatchCounts AS pmc
    ON ptr.player_id = pmc.player_id
JOIN main.player AS p
    ON ptr.player_id = p.player_id
ORDER BY
    batting_average DESC
LIMIT 5