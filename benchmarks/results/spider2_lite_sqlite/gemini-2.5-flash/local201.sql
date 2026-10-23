WITH Chars4 AS (
    SELECT
        words,
        SUBSTR(words, 1, 1) AS c1,
        SUBSTR(words, 2, 1) AS c2,
        SUBSTR(words, 3, 1) AS c3,
        SUBSTR(words, 4, 1) AS c4,
        NULL AS c5
    FROM main.word_list
    WHERE LENGTH(words) = 4 AND words LIKE 'r%'
),
Chars5 AS (
    SELECT
        words,
        SUBSTR(words, 1, 1) AS c1,
        SUBSTR(words, 2, 1) AS c2,
        SUBSTR(words, 3, 1) AS c3,
        SUBSTR(words, 4, 1) AS c4,
        SUBSTR(words, 5, 1) AS c5
    FROM main.word_list
    WHERE LENGTH(words) = 5 AND words LIKE 'r%'
),
AllFilteredWords AS (
    SELECT words, c1, c2, c3, c4, c5 FROM Chars4
    UNION ALL
    SELECT words, c1, c2, c3, c4, c5 FROM Chars5
),
SortedWords AS (
    SELECT
        words,
        (SELECT GROUP_CONCAT(c, '') FROM (
            SELECT c1 AS c
            UNION ALL SELECT c2
            UNION ALL SELECT c3
            UNION ALL SELECT c4
            UNION ALL SELECT c5 WHERE c5 IS NOT NULL
            ORDER BY c
        )) AS sorted_word
    FROM AllFilteredWords
),
AnagramCounts AS (
    SELECT
        sorted_word,
        COUNT(words) AS anagram_count
    FROM SortedWords
    GROUP BY sorted_word
    HAVING COUNT(words) > 1
)
SELECT
    sw.words,
    ac.anagram_count - 1 AS anagram_count
FROM SortedWords sw
JOIN AnagramCounts ac ON sw.sorted_word = ac.sorted_word
ORDER BY sw.words
LIMIT 10