WITH player_runs_per_season AS (
  SELECT
    m.season_id,
    bb.striker AS player_id,
    SUM(bs.runs_scored) AS total_runs
  FROM main.batsman_scored AS bs
  JOIN main.ball_by_ball AS bb
    ON bs.match_id = bb.match_id
    AND bs.over_id = bb.over_id
    AND bs.ball_id = bb.ball_id
    AND bs.innings_no = bb.innings_no
  JOIN main.match AS m
    ON bb.match_id = m.match_id
  GROUP BY
    m.season_id,
    bb.striker
), ranked_batsmen AS (
  SELECT
    season_id,
    player_id,
    total_runs,
    ROW_NUMBER() OVER (PARTITION BY season_id ORDER BY total_runs DESC, player_id ASC) AS rn
  FROM player_runs_per_season
), top_3_batsmen AS (
  SELECT
    rb.season_id,
    rb.rn,
    p.player_name AS batsman_name,
    rb.total_runs
  FROM ranked_batsmen AS rb
  JOIN main.player AS p
    ON rb.player_id = p.player_id
  WHERE
    rb.rn <= 3
), player_wickets_per_season AS (
  SELECT
    m.season_id,
    bb.bowler AS player_id,
    COUNT(wt.match_id) AS total_wickets
  FROM main.wicket_taken AS wt
  JOIN main.ball_by_ball AS bb
    ON wt.match_id = bb.match_id
    AND wt.over_id = bb.over_id
    AND wt.ball_id = bb.ball_id
    AND wt.innings_no = bb.innings_no
  JOIN main.match AS m
    ON bb.match_id = m.match_id
  WHERE
    wt.kind_out NOT IN ('run out', 'hit wicket', 'retired hurt')
  GROUP BY
    m.season_id,
    bb.bowler
), ranked_bowlers AS (
  SELECT
    season_id,
    player_id,
    total_wickets,
    ROW_NUMBER() OVER (PARTITION BY season_id ORDER BY total_wickets DESC, player_id ASC) AS rn
  FROM player_wickets_per_season
), top_3_bowlers AS (
  SELECT
    rb.season_id,
    rb.rn,
    p.player_name AS bowler_name,
    rb.total_wickets
  FROM ranked_bowlers AS rb
  JOIN main.player AS p
    ON rb.player_id = p.player_id
  WHERE
    rb.rn <= 3
)
SELECT
  tb.season_id,
  tb.rn,
  tb.batsman_name,
  tb.total_runs,
  tbo.bowler_name,
  tbo.total_wickets
FROM top_3_batsmen AS tb
JOIN top_3_bowlers AS tbo
  ON tb.season_id = tbo.season_id
  AND tb.rn = tbo.rn
ORDER BY
  tb.season_id ASC,
  tb.rn ASC