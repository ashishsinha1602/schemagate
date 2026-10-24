WITH label_counts AS (
  SELECT
    o.period AS period,
    l.description AS label,
    COUNT(DISTINCT o.object_id) AS artwork_count
  FROM `bigquery-public-data.the_met.objects` AS o
  JOIN `bigquery-public-data.the_met.vision_api_data` AS v
    ON o.object_id = v.object_id
  CROSS JOIN UNNEST(v.labelAnnotations) AS l
  WHERE o.period IS NOT NULL
    AND o.period != ''
    AND l.description IS NOT NULL
  GROUP BY o.period, l.description
  HAVING COUNT(DISTINCT o.object_id) >= 500
),
ranked AS (
  SELECT
    period,
    label,
    artwork_count,
    ROW_NUMBER() OVER (PARTITION BY period ORDER BY artwork_count DESC, label) AS rn
  FROM label_counts
)
SELECT period, label, artwork_count
FROM ranked
WHERE rn <= 3
ORDER BY period, artwork_count DESC, label