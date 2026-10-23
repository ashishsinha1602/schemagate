WITH PlayerRuns AS (
    SELECT
        bbb.striker AS player_id,
        SUM(bs.runs_scored) AS total_runs
    FROM
        main.batsman_scored AS bs
    JOIN
        main.ball_by_ball AS bbb
        ON bs.match_id = bbb.match_id
        AND bs.over_id = bbb.over_id
        AND bs.ball_id = bbb.ball_id
        AND bs.innings_no = bbb.innings_no
    JOIN
        main.match AS m
        ON bs.match_id = m.match_id
    WHERE
        m.season_id = 5
    GROUP BY
        bbb.striker
),
PlayerInningsBatted AS (
    SELECT
        bbb.striker AS player_id,
        COUNT(DISTINCT bbb.match_id || '-' || bbb.innings_no) AS innings_batted
    FROM
        main.ball_by_ball AS bbb
    JOIN
        main.match AS m
        ON bbb.match_id = m.match_id
    WHERE
        m.season_id = 5
    GROUP BY
        bbb.striker
)
SELECT
    p.player_name,
    CAST(pr.total_runs AS REAL) / pib.innings_batted AS batting_average
FROM
    PlayerRuns AS pr
JOIN
    PlayerInningsBatted AS pib
    ON pr.player_id = pib.player_id
JOIN
    main.player AS p
    ON pr.player_id = p.player_id
ORDER BY
    batting_average DESC
LIMIT 5