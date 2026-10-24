WITH t AS (
  SELECT
    CASE
      WHEN UPPER(r.TargetCompID) LIKE '%LUCKY%' THEN 'lucky'
      WHEN UPPER(r.TargetCompID) LIKE '%MOMO%' THEN 'momentum'
    END AS strategy,
    r.LastPx - r.StrikePrice AS intrinsic_value
  FROM `bigquery-public-data.cymbal_investments.trade_capture_report` AS r, UNNEST(r.Sides) AS s
  WHERE s.Side = '1'
)
SELECT
  AVG(IF(strategy = 'lucky', intrinsic_value, NULL)) - AVG(IF(strategy = 'momentum', intrinsic_value, NULL)) AS avg_intrinsic_value_difference
FROM t
WHERE strategy IS NOT NULL