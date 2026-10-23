WITH FirstTerms AS (
    SELECT
        lt.id_bioguide,
        l.gender,
        lt.state,
        CAST(strftime('%Y', lt.term_start) AS INTEGER) AS first_term_start_year
    FROM
        main.legislators_terms lt
    JOIN
        main.legislators l ON lt.id_bioguide = l.id_bioguide
    WHERE
        lt.term_number = 1
),
Intervals AS (
    SELECT 0 AS years_offset UNION ALL
    SELECT 2 UNION ALL
    SELECT 4 UNION ALL
    SELECT 6 UNION ALL
    SELECT 8 UNION ALL
    SELECT 10
),
-- Generate all combinations of legislator, state, gender, and retention date for each interval
LegislatorRetentionDates AS (
    SELECT
        ft.id_bioguide,
        ft.gender,
        ft.state,
        i.years_offset,
        (ft.first_term_start_year + i.years_offset) || '-12-31' AS retention_date_str
    FROM
        FirstTerms ft
    CROSS JOIN
        Intervals i
),
-- Identify which legislators were actually retained at each specific retention date
-- A legislator is retained if any of their terms overlap with the retention_date_str
RetainedLegislators AS (
    SELECT DISTINCT
        lrd.id_bioguide,
        lrd.gender,
        lrd.state,
        lrd.years_offset
    FROM
        LegislatorRetentionDates lrd
    JOIN
        main.legislators_terms lt_all ON lrd.id_bioguide = lt_all.id_bioguide
    WHERE
        lt_all.term_start <= lrd.retention_date_str AND
        lt_all.term_end >= lrd.retention_date_str
),
-- Count retained legislators by state, gender, and interval
RetentionSummary AS (
    SELECT
        rl.state,
        rl.gender,
        rl.years_offset,
        COUNT(DISTINCT rl.id_bioguide) AS retained_legislators_count
    FROM
        RetainedLegislators rl
    GROUP BY
        rl.state,
        rl.gender,
        rl.years_offset
),
-- Filter for intervals where retention count is greater than zero
FilteredRetention AS (
    SELECT
        state,
        gender,
        years_offset
    FROM
        RetentionSummary
    WHERE
        retained_legislators_count > 0
),
-- Count how many intervals (0, 2, 4, 6, 8, 10) have non-zero retention for each state and gender
GenderIntervalCounts AS (
    SELECT
        state,
        gender,
        COUNT(DISTINCT years_offset) AS num_intervals_retained
    FROM
        FilteredRetention
    GROUP BY
        state,
        gender
    HAVING
        num_intervals_retained = 6 -- Must have non-zero retention for all 6 intervals
)
-- Final selection: states where both genders satisfy the 6-interval condition
SELECT
    state
FROM
    GenderIntervalCounts
GROUP BY
    state
HAVING
    COUNT(DISTINCT gender) = 2 -- Both 'M' and 'F' must satisfy the condition
ORDER BY
    state