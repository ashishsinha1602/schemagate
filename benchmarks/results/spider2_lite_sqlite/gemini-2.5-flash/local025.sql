WITH BallRuns AS (
    SELECT
        bb.match_id,
        bb.innings_no,
        bb.over_id,
        bb.ball_id,
        bb.bowler,
        COALESCE(bs.runs_scored, 0) + COALESCE(er.extra_runs, 0) AS total_ball_runs
    FROM
        main.ball_by_ball AS bb
    LEFT JOIN
        main.batsman_scored AS bs ON bb.match_id = bs.match_id AND bb.innings_no = bs.innings_no AND bb.over_id = bs.over_id AND bb.ball_id = bs.ball_id
    LEFT JOIN
        main.extra_runs AS er ON bb.match_id = er.match_id AND bb.innings_no = er.innings_no AND bb.over_id = er.over_id AND bb.ball_id = er.ball_id
),
OverBowlerBalls AS (
    SELECT
        match_id,
        innings_no,
        over_id,
        bowler,
        COUNT(ball_id) AS balls_bowled,
        ROW_NUMBER() OVER (PARTITION BY match_id, innings_no, over_id ORDER BY COUNT(ball_id) DESC, bowler ASC) AS rn_bowler
    FROM
        BallRuns
    GROUP BY
        match_id,
        innings_no,
        over_id,
        bowler
),
PrimaryOverBowler AS (
    SELECT
        match_id,
        innings_no,
        over_id,
        bowler AS primary_bowler_id
    FROM
        OverBowlerBalls
    WHERE
        rn_bowler = 1
),
OverTotalRuns AS (
    SELECT
        br.match_id,
        br.innings_no,
        br.over_id,
        SUM(br.total_ball_runs) AS total_over_runs,
        pob.primary_bowler_id
    FROM
        BallRuns AS br
    JOIN
        PrimaryOverBowler AS pob ON br.match_id = pob.match_id AND br.innings_no = pob.innings_no AND br.over_id = pob.over_id
    GROUP BY
        br.match_id,
        br.innings_no,
        br.over_id,
        pob.primary_bowler_id
),
RankedHighestOvers AS (
    SELECT
        match_id,
        innings_no,
        total_over_runs,
        primary_bowler_id,
        ROW_NUMBER() OVER (PARTITION BY match_id, innings_no ORDER BY total_over_runs DESC, over_id ASC) AS rn
    FROM
        OverTotalRuns
)
SELECT
    AVG(total_over_runs)
FROM
    RankedHighestOvers
WHERE
    rn = 1