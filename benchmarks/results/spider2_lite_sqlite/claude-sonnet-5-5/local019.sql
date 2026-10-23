SELECT w1.name AS winner, w2.name AS loser
FROM Matches m
JOIN Belts b ON b.id = m.title_id
JOIN Wrestlers w1 ON w1.id = m.winner_id
JOIN Wrestlers w2 ON w2.id = m.loser_id
WHERE b.name LIKE '%NXT%'
  AND m.title_change = 0
  AND m.duration IS NOT NULL
  AND m.duration <> ''
ORDER BY length(m.duration), m.duration
LIMIT 1