WITH q AS (
  SELECT id, creation_date
  FROM `bigquery-public-data.stackoverflow.posts_questions`
  WHERE creation_date >= TIMESTAMP('2021-01-01') AND creation_date < TIMESTAMP('2022-01-01')
),
first_answer AS (
  SELECT a.parent_id AS question_id, MIN(a.creation_date) AS first_answer_date
  FROM `bigquery-public-data.stackoverflow.posts_answers` a
  GROUP BY a.parent_id
)
SELECT
  FORMAT_TIMESTAMP('%A', q.creation_date) AS day_of_week,
  COUNT(*) AS question_count,
  COUNTIF(fa.first_answer_date IS NOT NULL AND TIMESTAMP_DIFF(fa.first_answer_date, q.creation_date, SECOND) <= 3600) AS answered_within_one_hour,
  SAFE_DIVIDE(COUNTIF(fa.first_answer_date IS NOT NULL AND TIMESTAMP_DIFF(fa.first_answer_date, q.creation_date, SECOND) <= 3600), COUNT(*)) * 100 AS percentage_answered_within_one_hour
FROM q
LEFT JOIN first_answer fa ON fa.question_id = q.id
GROUP BY day_of_week, EXTRACT(DAYOFWEEK FROM q.creation_date)
ORDER BY EXTRACT(DAYOFWEEK FROM q.creation_date)