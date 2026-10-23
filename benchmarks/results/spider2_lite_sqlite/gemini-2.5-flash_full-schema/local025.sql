WITH AllRuns AS (
    SELECT
        match_id,
        innings_no,
        over_id,
        ball_id,
        runs_scored AS runs
    FROM main.batsman_scored
    UNION ALL
    SELECT
        match_id,
        innings_no,
        over_id,
        ball_id,
        extra_runs AS runs
    FROM main.extra_runs
),
OverRunsWithBowler AS (
    SELECT
        ar.match_id,
        ar.innings_no,
        ar.over_id,
        SUM(ar.runs) AS total_over_runs,
        MIN(bbb.bowler) AS bowler_id -- Assuming one bowler per over, pick one if multiple entries exist
    FROM AllRuns AS ar
    JOIN main.ball_by_ball AS bbb
        ON ar.match_id = bbb.match_id
        AND ar.innings_no = bbb.innings_no
        AND ar.over_id = bbb.over_id
        AND ar.ball_id = bbb.ball_id
    GROUP BY
        ar.match_id,
        ar.innings_no,
        ar.over_id
),
RankedOvers AS (
    SELECT
        match_id,
        innings_no,
        over_id,
        total_over_runs,
        bowler_id,
        RANK() OVER (PARTITION BY match_id, innings_no ORDER BY total_over_runs DESC) as rn
    FROM OverRunsWithBowler
)
SELECT
    AVG(total_over_runs)
FROM RankedOvers
WHERE rn = 1