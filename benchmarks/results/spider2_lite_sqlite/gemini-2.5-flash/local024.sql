WITH PlayerStats AS (
    SELECT
        p.player_id,
        p.country_name,
        SUM(CASE WHEN bb.striker = p.player_id THEN bs.runs_scored ELSE 0 END) AS total_runs_scored,
        COUNT(DISTINCT pm.match_id) AS total_matches_played
    FROM main.player AS p
    JOIN main.player_match AS pm
        ON p.player_id = pm.player_id
    LEFT JOIN main.ball_by_ball AS bb
        ON pm.match_id = bb.match_id AND p.player_id = bb.striker
    LEFT JOIN main.batsman_scored AS bs
        ON bb.match_id = bs.match_id
        AND bb.over_id = bs.over_id
        AND bb.ball_id = bs.ball_id
        AND bb.innings_no = bs.innings_no
    GROUP BY
        p.player_id,
        p.country_name
)
SELECT
    ps.country_name,
    AVG(CAST(ps.total_runs_scored AS REAL) / ps.total_matches_played) AS country_batting_average
FROM PlayerStats AS ps
WHERE ps.total_matches_played > 0
GROUP BY
    ps.country_name
ORDER BY
    country_batting_average DESC
LIMIT 5