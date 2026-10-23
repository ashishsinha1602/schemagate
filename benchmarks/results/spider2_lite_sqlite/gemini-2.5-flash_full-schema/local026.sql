WITH over_runs AS (
    SELECT
        bbb.match_id,
        bbb.innings_no,
        bbb.over_id,
        bbb.bowler,
        SUM(COALESCE(bs.runs_scored, 0)) +
        SUM(CASE WHEN er.extra_type IN ('wides', 'noballs') THEN COALESCE(er.extra_runs, 0) ELSE 0 END) AS total_runs_conceded
    FROM
        main.ball_by_ball AS bbb
    LEFT JOIN
        main.batsman_scored AS bs ON bbb.match_id = bs.match_id
                                  AND bbb.innings_no = bs.innings_no
                                  AND bbb.over_id = bs.over_id
                                  AND bbb.ball_id = bs.ball_id
    LEFT JOIN
        main.extra_runs AS er ON bbb.match_id = er.match_id
                              AND bbb.innings_no = er.innings_no
                              AND bbb.over_id = er.over_id
                              AND bbb.ball_id = er.ball_id
    GROUP BY
        bbb.match_id,
        bbb.innings_no,
        bbb.over_id,
        bbb.bowler
),
max_runs_per_match_over AS (
    SELECT
        match_id,
        MAX(total_runs_conceded) AS max_match_over_runs
    FROM
        over_runs
    GROUP BY
        match_id
),
filtered_max_overs AS (
    SELECT
        oruns.match_id,
        oruns.bowler,
        oruns.total_runs_conceded
    FROM
        over_runs AS oruns
    JOIN
        max_runs_per_match_over AS mrmo ON oruns.match_id = mrmo.match_id
                                        AND oruns.total_runs_conceded = mrmo.max_match_over_runs
),
bowler_ranked_max_overs AS (
    SELECT
        bowler,
        match_id,
        total_runs_conceded,
        ROW_NUMBER() OVER (PARTITION BY bowler ORDER BY total_runs_conceded DESC, match_id) AS rn
    FROM
        filtered_max_overs
),
top_bowler_performance AS (
    SELECT
        bowler,
        match_id,
        total_runs_conceded
    FROM
        bowler_ranked_max_overs
    WHERE
        rn = 1
),
final_ranked_bowlers AS (
    SELECT
        p.player_name,
        tbp.match_id,
        tbp.total_runs_conceded,
        DENSE_RANK() OVER (ORDER BY tbp.total_runs_conceded DESC) AS rnk
    FROM
        top_bowler_performance AS tbp
    JOIN
        main.player AS p ON tbp.bowler = p.player_id
)
SELECT
    player_name,
    match_id,
    total_runs_conceded
FROM
    final_ranked_bowlers
WHERE
    rnk <= 3
ORDER BY
    total_runs_conceded DESC,
    player_name,
    match_id