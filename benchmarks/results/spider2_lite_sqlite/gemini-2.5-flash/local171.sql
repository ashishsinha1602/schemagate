WITH RECURSIVE years_elapsed_range(y_elapsed) AS (
    SELECT 31
    UNION ALL
    SELECT y_elapsed + 1 FROM years_elapsed_range WHERE y_elapsed < 49
),
legislator_first_term AS (
    SELECT
        l.id_bioguide,
        CAST(SUBSTR(MIN(lt.term_start), 1, 4) AS INTEGER) AS first_term_start_year
    FROM main.legislators AS l
    JOIN main.legislators_terms AS lt
        ON l.id_bioguide = lt.id_bioguide
    WHERE
        l.gender = 'M' AND lt.state = 'LA'
    GROUP BY
        l.id_bioguide
)
SELECT
    yer.y_elapsed,
    COUNT(DISTINCT lft.id_bioguide)
FROM years_elapsed_range AS yer
CROSS JOIN legislator_first_term AS lft
JOIN main.legislators_terms AS lt_active
    ON lft.id_bioguide = lt_active.id_bioguide
WHERE
    (lft.first_term_start_year + yer.y_elapsed) || '-12-31' >= lt_active.term_start
    AND
    (lft.first_term_start_year + yer.y_elapsed) || '-12-31' <= lt_active.term_end
GROUP BY
    yer.y_elapsed
ORDER BY
    yer.y_elapsed