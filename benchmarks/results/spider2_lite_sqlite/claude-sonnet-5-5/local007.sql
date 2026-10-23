WITH spans AS (
  SELECT player_id,
    ABS(CAST(substr(final_game,1,4) AS INTEGER) - CAST(substr(debut,1,4) AS INTEGER)) AS y,
    ABS(CAST(substr(final_game,6,2) AS INTEGER) - CAST(substr(debut,6,2) AS INTEGER)) AS m,
    ABS(CAST(substr(final_game,9,2) AS INTEGER) - CAST(substr(debut,9,2) AS INTEGER)) AS d
  FROM player
  WHERE debut IS NOT NULL AND debut <> '' AND final_game IS NOT NULL AND final_game <> ''
)
SELECT CAST(AVG(ROUND(y, 2) + ROUND(m / 12.0, 2) + ROUND(d / 365.0, 2)) AS REAL) AS avg_career_span
FROM spans