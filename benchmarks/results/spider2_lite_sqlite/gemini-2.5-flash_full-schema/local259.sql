WITH player_roles_cte AS (
    SELECT
        pm.player_id,
        pm.role,
        COUNT(*) AS role_count,
        ROW_NUMBER() OVER (PARTITION BY pm.player_id ORDER BY COUNT(*) DESC, pm.role ASC) AS rn
    FROM main.player_match AS pm
    GROUP BY pm.player_id, pm.role
),
most_frequent_role_cte AS (
    SELECT
        pr.player_id,
        pr.role AS most_frequent_role
    FROM player_roles_cte AS pr
    WHERE pr.rn = 1
),
batting_summary_cte AS (
    SELECT
        bb.striker AS player_id,
        SUM(bs.runs_scored) AS total_runs_scored,
        COUNT(*) AS total_balls_faced
    FROM main.ball_by_ball AS bb
    JOIN main.batsman_scored AS bs
        ON bb.match_id = bs.match_id
        AND bb.over_id = bs.over_id
        AND bb.ball_id = bs.ball_id
        AND bb.innings_no = bs.innings_no
    GROUP BY bb.striker
),
dismissals_cte AS (
    SELECT
        wt.player_out AS player_id,
        COUNT(*) AS total_dismissals
    FROM main.wicket_taken AS wt
    GROUP BY wt.player_out
),
per_match_batting_scores_cte AS (
    SELECT
        bb.striker AS player_id,
        bb.match_id,
        SUM(bs.runs_scored) AS match_runs
    FROM main.ball_by_ball AS bb
    JOIN main.batsman_scored AS bs
        ON bb.match_id = bs.match_id
        AND bb.over_id = bs.over_id
        AND bb.ball_id = bs.ball_id
        AND bb.innings_no = bs.innings_no
    GROUP BY bb.striker, bb.match_id
),
batting_milestones_cte AS (
    SELECT
        player_id,
        MAX(match_runs) AS highest_score,
        SUM(CASE WHEN match_runs >= 30 THEN 1 ELSE 0 END) AS matches_30_plus,
        SUM(CASE WHEN match_runs >= 50 THEN 1 ELSE 0 END) AS matches_50_plus,
        SUM(CASE WHEN match_runs >= 100 THEN 1 ELSE 0 END) AS matches_100_plus
    FROM per_match_batting_scores_cte
    GROUP BY player_id
),
matches_played_cte AS (
    SELECT
        pm.player_id,
        COUNT(DISTINCT pm.match_id) AS total_matches_played
    FROM main.player_match AS pm
    GROUP BY pm.player_id
),
bowling_summary_cte AS (
    SELECT
        bb.bowler AS player_id,
        COALESCE(SUM(bs.runs_scored), 0) AS total_runs_conceded,
        COUNT(*) AS total_balls_bowled
    FROM main.ball_by_ball AS bb
    LEFT JOIN main.batsman_scored AS bs
        ON bb.match_id = bs.match_id
        AND bb.over_id = bs.over_id
        AND bb.ball_id = bs.ball_id
        AND bb.innings_no = bs.innings_no
    GROUP BY bb.bowler
),
bowler_wickets_cte AS (
    SELECT
        bb.bowler AS player_id,
        COUNT(wt.player_out) AS total_wickets_taken
    FROM main.ball_by_ball AS bb
    JOIN main.wicket_taken AS wt
        ON bb.match_id = wt.match_id
        AND bb.over_id = wt.over_id
        AND bb.ball_id = wt.ball_id
        AND bb.innings_no = wt.innings_no
    WHERE wt.kind_out NOT IN ('run out', 'obstructing the field', 'retired hurt', 'stumped')
    GROUP BY bb.bowler
),
per_match_bowling_performance_cte AS (
    SELECT
        bb.bowler AS player_id,
        bb.match_id,
        COALESCE(SUM(bs.runs_scored), 0) AS runs_conceded_in_match,
        COUNT(CASE WHEN wt.kind_out IS NOT NULL AND wt.kind_out NOT IN ('run out', 'obstructing the field', 'retired hurt', 'stumped') THEN 1 END) AS wickets_taken_in_match
    FROM main.ball_by_ball AS bb
    LEFT JOIN main.batsman_scored AS bs
        ON bb.match_id = bs.match_id
        AND bb.over_id = bs.over_id
        AND bb.ball_id = bs.ball_id
        AND bb.innings_no = bs.innings_no
    LEFT JOIN main.wicket_taken AS wt
        ON bb.match_id = wt.match_id
        AND bb.over_id = wt.over_id
        AND bb.ball_id = wt.ball_id
        AND bb.innings_no = wt.innings_no
    GROUP BY bb.bowler, bb.match_id
),
best_bowling_performance_ranked_cte AS (
    SELECT
        player_id,
        wickets_taken_in_match,
        runs_conceded_in_match,
        ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY wickets_taken_in_match DESC, runs_conceded_in_match ASC) AS rn
    FROM per_match_bowling_performance_cte
),
final_best_bowling_cte AS (
    SELECT
        player_id,
        CAST(wickets_taken_in_match AS TEXT) || '-' || CAST(runs_conceded_in_match AS TEXT) AS best_bowling_performance
    FROM best_bowling_performance_ranked_cte
    WHERE rn = 1
)
SELECT
    p.player_id,
    p.player_name,
    mfr.most_frequent_role,
    p.batting_hand,
    p.bowling_skill,
    COALESCE(bs.total_runs_scored, 0) AS total_runs_scored,
    COALESCE(mp.total_matches_played, 0) AS total_matches_played,
    COALESCE(d.total_dismissals, 0) AS total_times_dismissed,
    CASE
        WHEN COALESCE(d.total_dismissals, 0) > 0 THEN ROUND(CAST(COALESCE(bs.total_runs_scored, 0) AS REAL) / d.total_dismissals, 2)
        ELSE NULL
    END AS batting_average,
    COALESCE(bm.highest_score, 0) AS highest_score_in_a_single_match,
    COALESCE(bm.matches_30_plus, 0) AS matches_30_runs,
    COALESCE(bm.matches_50_plus, 0) AS matches_50_runs,
    COALESCE(bm.matches_100_plus, 0) AS matches_100_runs,
    COALESCE(bs.total_balls_faced, 0) AS total_balls_faced_career,
    CASE
        WHEN COALESCE(bs.total_balls_faced, 0) > 0 THEN ROUND(CAST(COALESCE(bs.total_runs_scored, 0) AS REAL) / bs.total_balls_faced * 100, 2)
        ELSE NULL
    END AS strike_rate,
    COALESCE(bw.total_wickets_taken, 0) AS total_wickets_taken,
    CASE
        WHEN COALESCE(bws.total_balls_bowled, 0) > 0 THEN ROUND(CAST(COALESCE(bws.total_runs_conceded, 0) AS REAL) / (bws.total_balls_bowled / 6.0), 2)
        ELSE NULL
    END AS economy_rate,
    fbb.best_bowling_performance
FROM main.player AS p
LEFT JOIN most_frequent_role_cte AS mfr ON p.player_id = mfr.player_id
LEFT JOIN batting_summary_cte AS bs ON p.player_id = bs.player_id
LEFT JOIN dismissals_cte AS d ON p.player_id = d.player_id
LEFT JOIN batting_milestones_cte AS bm ON p.player_id = bm.player_id
LEFT JOIN matches_played_cte AS mp ON p.player_id = mp.player_id
LEFT JOIN bowling_summary_cte AS bws ON p.player_id = bws.player_id
LEFT JOIN bowler_wickets_cte AS bw ON p.player_id = bw.player_id
LEFT JOIN final_best_bowling_cte AS fbb ON p.player_id = fbb.player_id