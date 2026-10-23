WITH bowler_runs AS (
    SELECT
        bb.bowler AS bowler_id,
        SUM(COALESCE(bs.runs_scored, 0) + COALESCE(CASE WHEN er.extra_type IN ('wides', 'noballs') THEN er.extra_runs ELSE 0 END, 0)) AS total_runs_conceded
    FROM main.ball_by_ball AS bb
    LEFT JOIN main.batsman_scored AS bs
        ON bb.match_id = bs.match_id
        AND bb.over_id = bs.over_id
        AND bb.ball_id = bs.ball_id
        AND bb.innings_no = bs.innings_no
    LEFT JOIN main.extra_runs AS er
        ON bb.match_id = er.match_id
        AND bb.over_id = er.over_id
        AND bb.ball_id = er.ball_id
        AND bb.innings_no = er.innings_no
    GROUP BY bb.bowler
),
bowler_wickets AS (
    SELECT
        bb.bowler AS bowler_id,
        COUNT(wt.player_out) AS total_wickets_taken
    FROM main.ball_by_ball AS bb
    JOIN main.wicket_taken AS wt
        ON bb.match_id = wt.match_id
        AND bb.over_id = wt.over_id
        AND bb.ball_id = wt.ball_id
        AND bb.innings_no = wt.innings_no
    WHERE wt.kind_out IN ('bowled', 'caught', 'caught and bowled', 'hit wicket', 'lbw', 'stumped')
    GROUP BY bb.bowler
)
SELECT
    p.player_name
FROM bowler_runs AS br
JOIN bowler_wickets AS bw
    ON br.bowler_id = bw.bowler_id
JOIN main.player AS p
    ON br.bowler_id = p.player_id
WHERE bw.total_wickets_taken > 0
ORDER BY CAST(br.total_runs_conceded AS REAL) / bw.total_wickets_taken ASC
LIMIT 1