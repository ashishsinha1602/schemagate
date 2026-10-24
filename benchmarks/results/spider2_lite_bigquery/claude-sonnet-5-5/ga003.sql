SELECT
  (SELECT ep.value.string_value FROM UNNEST(event_params) ep WHERE ep.key = 'board') AS board_type,
  AVG((SELECT ep.value.int_value FROM UNNEST(event_params) ep WHERE ep.key = 'score')) AS avg_score
FROM `firebase-public-project.analytics_153293282.events_*`
WHERE _TABLE_SUFFIX = '20180915'
  AND event_name = 'level_end_quickplay'
GROUP BY board_type
ORDER BY avg_score DESC