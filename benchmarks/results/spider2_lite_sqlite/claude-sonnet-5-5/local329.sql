SELECT COUNT(DISTINCT i.session) AS sessions
FROM form_log i
JOIN form_log c ON c.session = i.session
WHERE i.path = '/regist/input'
  AND c.path = '/regist/confirm'
  AND i.stamp < c.stamp