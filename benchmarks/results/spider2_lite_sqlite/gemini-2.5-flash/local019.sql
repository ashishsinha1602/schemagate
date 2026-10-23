WITH ParsedDurations AS (
  SELECT
    id,
    winner_id,
    loser_id,
    title_id,
    title_change,
    CASE
      WHEN duration IS NULL OR duration = '' THEN NULL
      WHEN INSTR(duration, ':') = 0 THEN CAST(duration AS INTEGER)
      WHEN INSTR(SUBSTR(duration, INSTR(duration, ':') + 1), ':') = 0 THEN
        CAST(SUBSTR(duration, 1, INSTR(duration, ':') - 1) AS INTEGER) * 60 +
        CAST(SUBSTR(duration, INSTR(duration, ':') + 1) AS INTEGER)
      ELSE
        CAST(SUBSTR(duration, 1, INSTR(duration, ':') - 1) AS INTEGER) * 3600 +
        CAST(SUBSTR(duration, INSTR(duration, ':') + 1, INSTR(SUBSTR(duration, INSTR(duration, ':') + 1), ':') - 1) AS INTEGER) * 60 +
        CAST(SUBSTR(duration, INSTR(duration, ':') + 1 + INSTR(SUBSTR(duration, INSTR(duration, ':') + 1), ':')) AS INTEGER)
    END AS duration_seconds
  FROM main.Matches
),
FilteredNXTMatches AS (
  SELECT
    pd.winner_id,
    pd.loser_id,
    pd.duration_seconds
  FROM ParsedDurations AS pd
  JOIN main.Belts AS b
    ON CAST(pd.title_id AS INTEGER) = b.id
  WHERE
    b.name LIKE '%NXT%' AND pd.title_change = 0 AND pd.duration_seconds IS NOT NULL
  ORDER BY
    pd.duration_seconds ASC
  LIMIT 1
)
SELECT
  w_winner.name,
  w_loser.name
FROM FilteredNXTMatches AS fnm
JOIN main.Wrestlers AS w_winner
  ON CAST(fnm.winner_id AS INTEGER) = w_winner.id
JOIN main.Wrestlers AS w_loser
  ON CAST(fnm.loser_id AS INTEGER) = w_loser.id