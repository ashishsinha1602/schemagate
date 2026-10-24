SELECT category, COUNT(DISTINCT original_url) AS url_count
FROM (
  SELECT
    i.original_url,
    CASE
      WHEN i.image_id IN (
        SELECT l.image_id
        FROM `bigquery-public-data.open_images.labels` l
        WHERE l.label_name = '/m/01yrx' AND l.confidence = 1
      ) THEN 'cat'
      WHEN i.image_id NOT IN (
        SELECT l.image_id
        FROM `bigquery-public-data.open_images.labels` l
        WHERE l.label_name = '/m/01yrx'
      ) THEN 'other'
      ELSE NULL
    END AS category
  FROM `bigquery-public-data.open_images.images` i
)
WHERE category IS NOT NULL
GROUP BY category