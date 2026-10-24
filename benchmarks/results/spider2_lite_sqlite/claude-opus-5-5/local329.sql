SELECT COUNT(DISTINCT i.session) AS session_count
FROM main.form_log AS i
JOIN main.form_log AS c
  ON c.session = i.session
 AND c.path = '/regist/confirm'
 AND c.stamp > i.stamp
WHERE i.path = '/regist/input'