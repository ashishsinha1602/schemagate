SELECT
  L1_model,
  COUNT(*) AS total_occurrences
FROM
  (
    SELECT
      L1_model
    FROM
      main.model
    UNION ALL
    SELECT
      L1_model
    FROM
      main.stack_ok
  ) AS combined_models
GROUP BY
  L1_model
ORDER BY
  total_occurrences DESC
LIMIT 1