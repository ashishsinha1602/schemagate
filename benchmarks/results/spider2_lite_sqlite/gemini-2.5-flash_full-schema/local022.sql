WITH PlayerCenturies AS (
  SELECT
    bbb.match_id,
    bbb.striker AS player_id,
    SUM(bs.runs_scored) AS total_runs
  FROM main.batsman_scored AS bs
  JOIN main.ball_by_ball AS bbb
    ON bs.match_id = bbb.match_id
    AND bs.over_id = bbb.over_id
    AND bs.ball_id = bbb.ball_id
    AND bs.innings_no = bbb.innings_no
  GROUP BY
    bbb.match_id,
    bbb.striker
  HAVING
    SUM(bs.runs_scored) >= 100
), PlayerTeamInMatch AS (
  SELECT
    pc.match_id,
    pc.player_id,
    pm.team_id AS player_team_id
  FROM PlayerCenturies AS pc
  JOIN main.player_match AS pm
    ON pc.match_id = pm.match_id
    AND pc.player_id = pm.player_id
)
SELECT DISTINCT
  p.player_name
FROM PlayerTeamInMatch AS ptim
JOIN main.match AS m
  ON ptim.match_id = m.match_id
JOIN main.player AS p
  ON ptim.player_id = p.player_id
WHERE
  ptim.player_team_id <> m.match_winner