WITH FirstTerms AS (
    SELECT
        id_bioguide,
        MIN(term_start) AS first_term_start
    FROM main.legislators_terms
    GROUP BY id_bioguide
),
Cohort AS (
    SELECT
        id_bioguide,
        first_term_start,
        CAST(SUBSTR(first_term_start, 1, 4) AS INTEGER) AS first_term_year
    FROM FirstTerms
    WHERE first_term_start BETWEEN '1917-01-01' AND '1999-12-31'
),
CohortSize AS (
    SELECT COUNT(DISTINCT id_bioguide) AS total_cohort_size
    FROM Cohort
),
YearsOffset AS (
    SELECT 1 AS year_offset
    UNION ALL
    SELECT year_offset + 1 FROM YearsOffset WHERE year_offset < 20
),
RetentionChecks AS (
    SELECT
        c.id_bioguide,
        yo.year_offset,
        (c.first_term_year + yo.year_offset) || '-12-31' AS measurement_date
    FROM Cohort c
    CROSS JOIN YearsOffset yo
),
RetainedLegislators AS (
    SELECT DISTINCT
        rc.year_offset,
        rc.id_bioguide
    FROM RetentionChecks rc
    JOIN main.legislators_terms lt ON rc.id_bioguide = lt.id_bioguide
    WHERE lt.term_start <= rc.measurement_date AND lt.term_end >= rc.measurement_date
)
SELECT
    yo.year_offset,
    CAST(COUNT(rl.id_bioguide) AS REAL) / cs.total_cohort_size AS retention_rate
FROM YearsOffset yo
CROSS JOIN CohortSize cs
LEFT JOIN RetainedLegislators rl ON yo.year_offset = rl.year_offset
GROUP BY yo.year_offset, cs.total_cohort_size
ORDER BY yo.year_offset