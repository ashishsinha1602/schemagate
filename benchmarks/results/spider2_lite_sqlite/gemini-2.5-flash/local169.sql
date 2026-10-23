WITH RECURSIVE YearsSequence(year_offset) AS (
    SELECT 1
    UNION ALL
    SELECT year_offset + 1
    FROM YearsSequence
    WHERE year_offset < 20
),
FirstTerms AS (
    SELECT
        id_bioguide,
        MIN(term_start) AS first_term_start
    FROM main.legislators_terms
    GROUP BY id_bioguide
),
CohortLegislators AS (
    SELECT
        ft.id_bioguide,
        ft.first_term_start
    FROM FirstTerms ft
    WHERE ft.first_term_start >= '1917-01-01' AND ft.first_term_start <= '1999-12-31'
),
TotalCohortSize AS (
    SELECT COUNT(DISTINCT id_bioguide) AS total_legislators
    FROM CohortLegislators
),
RetentionStatus AS (
    SELECT
        cl.id_bioguide,
        ys.year_offset,
        (CAST(SUBSTR(cl.first_term_start, 1, 4) AS INTEGER) + ys.year_offset) || '-12-31' AS check_date
    FROM CohortLegislators cl
    CROSS JOIN YearsSequence ys
),
LegislatorRetention AS (
    SELECT
        rs.year_offset,
        rs.id_bioguide,
        MAX(CASE
            WHEN lt.term_start <= rs.check_date AND lt.term_end >= rs.check_date THEN 1
            ELSE 0
        END) AS is_retained
    FROM RetentionStatus rs
    JOIN main.legislators_terms lt ON rs.id_bioguide = lt.id_bioguide
    GROUP BY rs.year_offset, rs.id_bioguide
)
SELECT
    ys.year_offset,
    CASE
        WHEN tcs.total_legislators = 0 THEN 0.0
        ELSE COALESCE(CAST(SUM(lr.is_retained) AS REAL), 0.0) / tcs.total_legislators
    END AS retention_rate
FROM YearsSequence ys
CROSS JOIN TotalCohortSize tcs
LEFT JOIN LegislatorRetention lr ON ys.year_offset = lr.year_offset
GROUP BY ys.year_offset, tcs.total_legislators
ORDER BY ys.year_offset