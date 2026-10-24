WITH w AS (
  SELECT DISTINCT words
  FROM main.word_list
  WHERE words IS NOT NULL AND length(words) BETWEEN 4 AND 5
),
chars(word, pos, ch) AS (
  SELECT words, 1, substr(words, 1, 1) FROM w
  UNION ALL
  SELECT word, pos + 1, substr(word, pos + 1, 1)
  FROM chars
  WHERE pos < length(word)
),
sig AS (
  SELECT word, group_concat(ch, '') AS s
  FROM (SELECT word, ch FROM chars ORDER BY word, ch)
  GROUP BY word
)
SELECT a.word, COUNT(b.word) AS anagram_count
FROM sig a
JOIN sig b
  ON a.s = b.s
 AND length(a.word) = length(b.word)
 AND a.word <> b.word
WHERE substr(a.word, 1, 1) = 'r'
GROUP BY a.word
ORDER BY a.word
LIMIT 10