WITH bowler_wickets AS (
    SELECT
        bb.bowler AS player_id,
        COUNT(wt.player_out) AS total_wickets
    FROM
        main.wicket_taken AS wt
    JOIN
        main.ball_by_ball AS bb
        ON wt.match_id = bb.match_id
        AND wt.over_id = bb.over_id
        AND wt.ball_id = bb.ball_id
        AND wt.innings_no = bb.innings_no
    WHERE
        wt.kind_out NOT IN ('run out', 'retired hurt', 'obstructing the field')
    GROUP BY
        bb.bowler
),
bowler_runs_balls AS (
    SELECT
        bb.bowler AS player_id,
        SUM(bs.runs_scored) AS total_runs_conceded,
        COUNT(bb.ball_id) AS total_balls_bowled
    FROM
        main.ball_by_ball AS bb
    JOIN
        main.batsman_scored AS bs
        ON bb.match_id = bs.match_id
        AND bb.over_id = bs.over_id
        AND bb.ball_id = bs.ball_id
        AND bb.innings_no = bs.innings_no
    GROUP BY
        bb.bowler
),
bowler_stats_base AS (
    SELECT
        p.player_id,
        p.player_name,
        COALESCE(bw.total_wickets, 0) AS total_wickets,
        COALESCE(brb.total_runs_conceded, 0) AS total_runs_conceded,
        COALESCE(brb.total_balls_bowled, 0) AS total_balls_bowled,
        CASE
            WHEN COALESCE(brb.total_balls_bowled, 0) > 0 THEN (COALESCE(brb.total_runs_conceded, 0) * 6.0) / COALESCE(brb.total_balls_bowled, 0)
            ELSE 0.0
        END AS economy_rate,
        CASE
            WHEN COALESCE(bw.total_wickets, 0) > 0 THEN COALESCE(brb.total_balls_bowled, 0) * 1.0 / COALESCE(bw.total_wickets, 0)
            ELSE 0.0
        END AS strike_rate
    FROM
        main.player AS p
    LEFT JOIN
        bowler_wickets AS bw
        ON p.player_id = bw.player_id
    LEFT JOIN
        bowler_runs_balls AS brb
        ON p.player_id = brb.player_id
    WHERE
        bw.player_id IS NOT NULL OR brb.player_id IS NOT NULL
),
match_bowling_performance AS (
    SELECT
        bb.bowler AS player_id,
        bb.match_id,
        SUM(bs.runs_scored) AS match_runs_conceded,
        COUNT(wt.player_out) AS match_wickets
    FROM
        main.ball_by_ball AS bb
    JOIN
        main.batsman_scored AS bs
        ON bb.match_id = bs.match_id
        AND bb.over_id = bs.over_id
        AND bb.ball_id = bs.ball_id
        AND bb.innings_no = bs.innings_no
    LEFT JOIN
        main.wicket_taken AS wt
        ON bb.match_id = wt.match_id
        AND bb.over_id = wt.over_id
        AND bb.ball_id = wt.ball_id
        AND bb.innings_no = wt.innings_no
        AND wt.kind_out NOT IN ('run out', 'retired hurt', 'obstructing the field')
    GROUP BY
        bb.bowler,
        bb.match_id
),
best_bowling_per_bowler AS (
    SELECT
        player_id,
        match_wickets,
        match_runs_conceded,
        RANK() OVER (PARTITION BY player_id ORDER BY match_wickets DESC, match_runs_conceded ASC) AS rn
    FROM
        match_bowling_performance
    WHERE
        match_wickets > 0
)
SELECT
    bsb.player_name,
    bsb.total_wickets,
    ROUND(bsb.economy_rate, 2) AS economy_rate,
    ROUND(bsb.strike_rate, 2) AS strike_rate,
    COALESCE(bbpb.best_bowling, '0-0') AS best_bowling
FROM
    bowler_stats_base AS bsb
LEFT JOIN
    (SELECT player_id, CAST(match_wickets AS TEXT) || '-' || CAST(match_runs_conceded AS TEXT) AS best_bowling FROM best_bowling_per_bowler WHERE rn = 1) AS bbpb
    ON bsb.player_id = bbpb.player_id
ORDER BY
    bsb.player_name