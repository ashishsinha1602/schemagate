WITH all_photos AS (
  SELECT user FROM `bigquery-public-data.eclipse_megamovie.photos_v_0_1`
  UNION ALL
  SELECT user FROM `bigquery-public-data.eclipse_megamovie.photos_v_0_2`
  UNION ALL
  SELECT user FROM `bigquery-public-data.eclipse_megamovie.photos_v_0_3`
)
SELECT user
FROM all_photos
GROUP BY user
ORDER BY COUNT(*) DESC
LIMIT 1