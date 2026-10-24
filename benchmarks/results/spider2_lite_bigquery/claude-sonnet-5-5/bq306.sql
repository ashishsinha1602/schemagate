WITH ans AS (
  SELECT a.id, a.parent_id
  FROM `bigquery-public-data.stackoverflow.posts_answers` a
  WHERE a.owner_user_id = 1908967
    AND a.creation_date < TIMESTAMP('2018-06-07')
),
ans_score AS (
  SELECT ans.parent_id,
         SUM(CASE WHEN v.vote_type_id = 2 THEN 10
                  WHEN v.vote_type_id = 1 THEN 15
                  ELSE 0 END) AS pts
  FROM ans
  JOIN `bigquery-public-data.stackoverflow.votes` v
    ON v.post_id = ans.id
  WHERE v.vote_type_id IN (1, 2)
  GROUP BY ans.id, ans.parent_id
)
SELECT tag,
       SUM(s.pts) AS score
FROM ans_score s
JOIN `bigquery-public-data.stackoverflow.posts_questions` q
  ON q.id = s.parent_id
CROSS JOIN UNNEST(SPLIT(q.tags, '|')) AS tag
GROUP BY tag
ORDER BY score DESC
LIMIT 10