WITH all_pitches AS (
  SELECT gameId, pitcherId, pitcherFirstName, pitcherLastName, pitchSpeed, lineupTeamId, lineupPlayerId
  FROM `bigquery-public-data.baseball.games_wide`
  UNION ALL
  SELECT gameId, pitcherId, pitcherFirstName, pitcherLastName, pitchSpeed, lineupTeamId, lineupPlayerId
  FROM `bigquery-public-data.baseball.games_post_wide`
),
pitcher_team AS (
  SELECT
    lineupTeamId AS teamId,
    pitcherId,
    pitcherFirstName,
    pitcherLastName,
    MAX(pitchSpeed) AS max_speed
  FROM all_pitches
  WHERE pitchSpeed > 0
    AND lineupPlayerId = pitcherId
  GROUP BY teamId, pitcherId, pitcherFirstName, pitcherLastName
),
ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY teamId ORDER BY max_speed DESC) AS rn
  FROM pitcher_team
)
SELECT
  CONCAT(pitcherFirstName, ' ', pitcherLastName) AS pitcher_name,
  max_speed AS max_pitch_speed
FROM ranked
WHERE rn = 1