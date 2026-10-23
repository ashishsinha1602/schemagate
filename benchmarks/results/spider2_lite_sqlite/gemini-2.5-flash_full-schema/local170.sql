WITH LegislatorTermInfo AS (
    SELECT
        l.id_bioguide,
        l.gender,
        lt.term_start,
        lt.term_end,
        lt.state,
        ROW_NUMBER() OVER (PARTITION BY l.id_bioguide ORDER BY lt.term_start) as rn
    FROM main.legislators AS l
    JOIN main.legislators_terms AS lt
        ON l.id_bioguide = lt.id_bioguide
),
LegislatorFirstTerm AS (
    SELECT
        id_bioguide,
        gender,
        term_start AS first_term_start_date,
        state AS first_term_state
    FROM LegislatorTermInfo
    WHERE rn = 1
),
AllIntervals AS (
    SELECT
        lft.id_bioguide,
        lft.gender,
        lft.first_term_state,
        CAST(SUBSTR(lft.first_term_start_date, 1, 4) AS INTEGER) AS first_term_start_year,
        intervals.interval_years
    FROM LegislatorFirstTerm AS lft
    CROSS JOIN (
        SELECT 0 AS interval_years
        UNION ALL SELECT 2
        UNION ALL SELECT 4
        UNION ALL SELECT 6
        UNION ALL SELECT 8
        UNION ALL SELECT 10
    ) AS intervals
),
LegislatorRetentionStatus AS (
    SELECT
        ai.id_bioguide,
        ai.gender,
        ai.first_term_state,
        ai.interval_years,
        CASE WHEN COUNT(lt.id_bioguide) > 0 THEN 1 ELSE 0 END AS is_retained
    FROM AllIntervals AS ai
    LEFT JOIN main.legislators_terms AS lt
        ON lt.id_bioguide = ai.id_bioguide
       AND lt.term_start <= (ai.first_term_start_year + ai.interval_years) || '-12-31'
       AND lt.term_end >= (ai.first_term_start_year + ai.interval_years) || '-12-31'
    GROUP BY
        ai.id_bioguide,
        ai.gender,
        ai.first_term_state,
        ai.interval_years
),
RetentionMetrics AS (
    SELECT
        lrs.first_term_state AS state,
        lrs.gender,
        lrs.interval_years,
        SUM(lrs.is_retained) AS retained_legislators_count
    FROM LegislatorRetentionStatus AS lrs
    GROUP BY
        lrs.first_term_state,
        lrs.gender,
        lrs.interval_years
),
SuccessfulIntervals AS (
    SELECT
        state,
        gender,
        interval_years
    FROM RetentionMetrics
    WHERE retained_legislators_count > 0
),
StateGenderIntervalCounts AS (
    SELECT
        state,
        gender,
        COUNT(DISTINCT interval_years) AS num_successful_intervals
    FROM SuccessfulIntervals
    GROUP BY
        state,
        gender
    HAVING COUNT(DISTINCT interval_years) = 6
),
FinalStates AS (
    SELECT
        state
    FROM StateGenderIntervalCounts
    GROUP BY
        state
    HAVING COUNT(DISTINCT gender) = 2
)
SELECT state FROM FinalStates