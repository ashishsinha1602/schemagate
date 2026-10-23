WITH BallRuns AS (
    SELECT
        bbb.match_id,
        bbb.innings_no,
        bbb.striker,
        bbb.non_striker,
        COALESCE(bs.runs_scored, 0) AS striker_runs,
        COALESCE(er.extra_runs, 0) AS partnership_extra_runs
    FROM main.ball_by_ball AS bbb
    LEFT JOIN main.batsman_scored AS bs
        ON bbb.match_id = bs.match_id
        AND bbb.over_id = bs.over_id
        AND bbb.ball_id = bs.ball_id
        AND bbb.innings_no = bs.innings_no
    LEFT JOIN main.extra_runs AS er
        ON bbb.match_id = er.match_id
        AND bbb.over_id = er.over_id
        AND bbb.ball_id = er.ball_id
        AND bbb.innings_no = er.innings_no
        AND er.extra_type IN ('wides', 'noballs') -- Only these add to partnership total without being batsman runs
    WHERE bbb.striker IS NOT NULL AND bbb.non_striker IS NOT NULL -- Ensure both players are present for a partnership
),
PartnershipAgg AS (
    SELECT
        match_id,
        MIN(striker, non_striker) AS player_a,
        MAX(striker, non_striker) AS player_b,
        SUM(CASE WHEN striker = MIN(striker, non_striker) THEN striker_runs ELSE 0 END) AS player_a_individual_runs,
        SUM(CASE WHEN striker = MAX(striker, non_striker) THEN striker_runs ELSE 0 END) AS player_b_individual_runs,
        SUM(striker_runs) + SUM(partnership_extra_runs) AS total_partnership_runs
    FROM BallRuns
    GROUP BY match_id, MIN(striker, non_striker), MAX(striker, non_striker)
),
RankedPartnerships AS (
    SELECT
        match_id,
        player_a,
        player_b,
        player_a_individual_runs,
        player_b_individual_runs,
        total_partnership_runs,
        RANK() OVER (PARTITION BY match_id ORDER BY total_partnership_runs DESC) AS rnk
    FROM PartnershipAgg
)
SELECT
    rp.match_id,
    CASE
        WHEN rp.player_a_individual_runs > rp.player_b_individual_runs THEN rp.player_a
        WHEN rp.player_b_individual_runs > rp.player_a_individual_runs THEN rp.player_b
        ELSE rp.player_b -- If scores are equal, player_b (MAX ID) is player 1
    END AS player_1_id,
    CASE
        WHEN rp.player_a_individual_runs > rp.player_b_individual_runs THEN rp.player_a_individual_runs
        WHEN rp.player_b_individual_runs > rp.player_a_individual_runs THEN rp.player_b_individual_runs
        ELSE rp.player_b_individual_runs -- If scores are equal, player_b's score is player 1's score
    END AS player_1_score,
    CASE
        WHEN rp.player_a_individual_runs > rp.player_b_individual_runs THEN rp.player_b
        WHEN rp.player_b_individual_runs > rp.player_a_individual_runs THEN rp.player_a
        ELSE rp.player_a -- If scores are equal, player_a (MIN ID) is player 2
    END AS player_2_id,
    CASE
        WHEN rp.player_a_individual_runs > rp.player_b_individual_runs THEN rp.player_b_individual_runs
        WHEN rp.player_b_individual_runs > rp.player_a_individual_runs THEN rp.player_a_individual_runs
        ELSE rp.player_a_individual_runs -- If scores are equal, player_a's score is player 2's score
    END AS player_2_score,
    rp.total_partnership_runs
FROM RankedPartnerships AS rp
WHERE rp.rnk = 1