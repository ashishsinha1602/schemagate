WITH ans AS (
  SELECT
    a.id,
    a.parent_id,
    a.owner_user_id,
    a.score,
    SUM(a.score) OVER (PARTITION BY a.parent_id) AS total_score,
    ROW_NUMBER() OVER (PARTITION BY a.parent_id ORDER BY a.score DESC, a.id) AS rn
  FROM `bigquery-public-data.stackoverflow.posts_answers` a
  WHERE a.parent_id IS NOT NULL
),
assoc AS (
  SELECT q.owner_user_id AS user_id, q.id AS question_id
  FROM `bigquery-public-data.stackoverflow.posts_questions` q
  WHERE q.owner_user_id IS NOT NULL
  UNION DISTINCT
  SELECT ans.owner_user_id AS user_id, q.id AS question_id
  FROM ans
  JOIN `bigquery-public-data.stackoverflow.posts_questions` q
    ON q.id = ans.parent_id
  WHERE ans.owner_user_id IS NOT NULL
    AND (
      ans.id = q.accepted_answer_id
      OR ans.score > 5
      OR (ans.score > 0 AND ans.score > 0.2 * ans.total_score)
      OR ans.rn <= 3
    )
)
SELECT
  assoc.user_id,
  u.display_name,
  SUM(q.view_count) AS total_view_count
FROM assoc
JOIN `bigquery-public-data.stackoverflow.posts_questions` q
  ON q.id = assoc.question_id
LEFT JOIN `bigquery-public-data.stackoverflow.users` u
  ON u.id = assoc.user_id
GROUP BY assoc.user_id, u.display_name
ORDER BY total_view_count DESC
LIMIT 10