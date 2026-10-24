SELECT CAST(AVG(career_span) AS REAL) AS avg_career_span
FROM (
  SELECT
    ROUND(ABS(CAST(substr(final_game, 1, 4) AS INTEGER) - CAST(substr(debut, 1, 4) AS INTEGER)), 2)
    + ROUND(ABS(CAST(substr(final_game, 6, 2) AS INTEGER) - CAST(substr(debut, 6, 2) AS INTEGER)) / 12.0, 2)
    + ROUND(ABS(CAST(substr(final_game, 9, 2) AS INTEGER) - CAST(substr(debut, 9, 2) AS INTEGER)) / 365.0, 2) AS career_span
  FROM player
  WHERE debut IS NOT NULL AND debut <> ''
    AND final_game IS NOT NULL AND final_game <> ''
) t