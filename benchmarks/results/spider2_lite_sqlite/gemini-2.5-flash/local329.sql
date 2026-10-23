WITH input_page_visits AS (
  SELECT
    session,
    stamp
  FROM main.form_log
  WHERE
    path = '/regist/input'
), confirm_page_visits AS (
  SELECT
    session,
    stamp
  FROM main.form_log
  WHERE
    path = '/regist/confirm'
)
SELECT
  COUNT(DISTINCT i.session)
FROM input_page_visits AS i
JOIN confirm_page_visits AS c
  ON i.session = c.session
WHERE
  i.stamp < c.stamp