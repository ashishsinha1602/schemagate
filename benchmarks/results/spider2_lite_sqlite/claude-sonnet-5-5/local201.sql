WITH RECURSIVE w AS (
  SELECT DISTINCT words FROM word_list WHERE length(words) BETWEEN 4 AND 5
),
chars(words, i, c) AS (
  SELECT words, 1, substr(words, 1, 1) FROM w
  UNION ALL
  SELECT words, i + 1, substr(words, i + 1, 1) FROM chars WHERE i < length(words)
),
sorted AS (
  SELECT words, group_concat(c, '') AS k
  FROM (SELECT words, c FROM chars ORDER BY words, c)
  GROUP BY words
)
SELECT a.words, COUNT(b.words) AS anagram_count
FROM sorted a
JOIN sorted b ON a.k = b.k AND a.words <> b.words
WHERE substr(a.words, 1, 1) = 'r'
GROUP BY a.words
ORDER BY a.words
LIMIT 10