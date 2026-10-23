WITH RECURSIVE char_positions(n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1 FROM char_positions WHERE n < 5
),
filtered_and_sorted AS (
    SELECT
        t1.words,
        GROUP_CONCAT(SUBSTR(t1.words, t2.n, 1), '') OVER (PARTITION BY t1.words ORDER BY SUBSTR(t1.words, t2.n, 1)) AS sorted_word
    FROM main.word_list AS t1
    JOIN char_positions AS t2 ON t2.n <= LENGTH(t1.words)
    WHERE LENGTH(t1.words) BETWEEN 4 AND 5
      AND t1.words LIKE 'r%'
),
anagram_groups AS (
    SELECT
        sorted_word,
        COUNT(DISTINCT words) AS group_size
    FROM filtered_and_sorted
    GROUP BY sorted_word
    HAVING COUNT(DISTINCT words) > 1
)
SELECT
    fs.words,
    ag.group_size - 1 AS anagram_count
FROM filtered_and_sorted fs
JOIN anagram_groups ag ON fs.sorted_word = ag.sorted_word
ORDER BY fs.words
LIMIT 10