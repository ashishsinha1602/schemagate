WITH BatsmanRuns AS (
    SELECT
        m.season_id,
        bb.striker AS player_id,
        p.player_name,
        SUM(bs.runs_scored) AS total_runs
    FROM main.ball_by_ball AS bb
    JOIN main.batsman_scored AS bs
        ON bb.match_id = bs.match_id
        AND bb.over_id = bs.over_id
        AND bb.ball_id = bs.ball_id
        AND bb.innings_no = bs.innings_no
    JOIN main.match AS m
        ON bb.match_id = m.match_id
    JOIN main.player AS p
        ON bb.striker = p.player_id
    GROUP BY
        m.season_id,
        bb.striker,
        p.player_name
),
RankedBatsmen AS (
    SELECT
        season_id,
        player_id,
        player_name,
        total_runs,
        ROW_NUMBER() OVER (PARTITION BY season_id ORDER BY total_runs DESC, player_id ASC) AS rn
    FROM BatsmanRuns
),
BowlerWickets AS (
    SELECT
        m.season_id,
        bb.bowler AS player_id,
        p.player_name,
        COUNT(*) AS total_wickets
    FROM main.ball_by_ball AS bb
    JOIN main.wicket_taken AS wt
        ON bb.match_id = wt.match_id
        AND bb.over_id = wt.over_id
        AND bb.ball_id = wt.ball_id
        AND bb.innings_no = wt.innings_no
    JOIN main.match AS m
        ON bb.match_id = m.match_id
    JOIN main.player AS p
        ON bb.bowler = p.player_id
    WHERE wt.kind_out NOT IN ('run out', 'hit wicket', 'retired hurt')
    GROUP BY
        m.season_id,
        bb.bowler,
        p.player_name
),
RankedBowlers AS (
    SELECT
        season_id,
        player_id,
        player_name,
        total_wickets,
        ROW_NUMBER() OVER (PARTITION BY season_id ORDER BY total_wickets DESC, player_id ASC) AS rn
    FROM BowlerWickets
)
SELECT
    rb.season_id,
    rb.player_name AS batsman_name,
    rb.total_runs AS batsman_runs,
    rbo.player_name AS bowler_name,
    rbo.total_wickets AS bowler_wickets
FROM RankedBatsmen AS rb
JOIN RankedBowlers AS rbo
    ON rb.season_id = rbo.season_id
    AND rb.rn = rbo.rn
WHERE rb.rn <= 3
ORDER BY
    rb.season_id ASC,
    rb.rn ASC