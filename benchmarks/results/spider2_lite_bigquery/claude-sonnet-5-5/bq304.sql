WITH filtered AS (
  SELECT
    q.id,
    q.title,
    q.view_count,
    tag
  FROM `bigquery-public-data.stackoverflow.posts_questions` q,
  UNNEST(SPLIT(q.tags, '|')) AS tag
  WHERE tag IN ('android-layout', 'android-activity', 'android-intent', 'android-edittext', 'android-fragments', 'android-recyclerview', 'listview', 'android-actionbar', 'google-maps', 'android-asynctask')
    AND LOWER(COALESCE(q.title, '')) LIKE '%how%'
    AND NOT REGEXP_CONTAINS(LOWER(COALESCE(q.title, '')), r'fail|problem|error|wrong|fix|bug|issue|solve|trouble')
),
ranked AS (
  SELECT
    tag,
    id,
    title,
    view_count,
    ROW_NUMBER() OVER (PARTITION BY tag ORDER BY view_count DESC) AS rn,
    COUNT(*) OVER (PARTITION BY tag) AS cnt
  FROM filtered
)
SELECT
  tag,
  id,
  title,
  view_count
FROM ranked
WHERE cnt >= 50
  AND rn <= 50
ORDER BY tag, view_count DESC