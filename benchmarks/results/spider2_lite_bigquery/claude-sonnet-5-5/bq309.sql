WITH good_answers AS (
  SELECT DISTINCT parent_id
  FROM `bigquery-public-data.stackoverflow.posts_answers`
  WHERE SAFE_DIVIDE(score, SAFE_CAST(view_count AS INT64)) > 0.01
),
top_q AS (
  SELECT
    q.id,
    q.owner_user_id,
    CHAR_LENGTH(q.body) AS body_len
  FROM `bigquery-public-data.stackoverflow.posts_questions` TABLESAMPLE SYSTEM (8 PERCENT) q
  WHERE q.owner_user_id IS NOT NULL
    AND (
      q.accepted_answer_id IS NOT NULL
      OR q.id IN (SELECT parent_id FROM good_answers)
    )
  ORDER BY body_len DESC
  LIMIT 10
),
badge_counts AS (
  SELECT b.user_id, COUNT(*) AS badge_count
  FROM `bigquery-public-data.stackoverflow.badges` b
  WHERE b.user_id IN (SELECT owner_user_id FROM top_q)
  GROUP BY b.user_id
)
SELECT
  u.reputation,
  u.up_votes - u.down_votes AS net_votes,
  IFNULL(bc.badge_count, 0) AS badge_count
FROM top_q t
JOIN `bigquery-public-data.stackoverflow.users` u
  ON t.owner_user_id = u.id
LEFT JOIN badge_counts bc
  ON bc.user_id = u.id
ORDER BY t.body_len DESC