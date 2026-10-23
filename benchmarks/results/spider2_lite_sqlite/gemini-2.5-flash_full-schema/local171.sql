WITH LegislatorFirstTerm AS (
    SELECT
        l.id_bioguide,
        CAST(SUBSTR(MIN(lt.term_start), 1, 4) AS INTEGER) AS first_term_start_year
    FROM
        main.legislators AS l
    JOIN
        main.legislators_terms AS lt
        ON l.id_bioguide = lt.id_bioguide
    WHERE
        l.gender = 'M' AND lt.state = 'LA'
    GROUP BY
        l.id_bioguide
),
YearsElapsed AS (
    SELECT (a.id - 1) + 31 AS years_since_first_term
    FROM main.aliens AS a
    WHERE (a.id - 1) + 31 <= 49
    LIMIT 19
),
LegislatorServiceYears AS (
    SELECT
        lft.id_bioguide,
        ye.years_since_first_term,
        (lft.first_term_start_year + ye.years_since_first_term) || '-12-31' AS target_date
    FROM
        LegislatorFirstTerm AS lft
    CROSS JOIN
        YearsElapsed AS ye
)
SELECT
    lsy.years_since_first_term,
    COUNT(DISTINCT lsy.id_bioguide) AS distinct_legislators_count
FROM
    LegislatorServiceYears AS lsy
JOIN
    main.legislators_terms AS lt
    ON lsy.id_bioguide = lt.id_bioguide
WHERE
    lt.term_start <= lsy.target_date AND lt.term_end >= lsy.target_date
GROUP BY
    lsy.years_since_first_term
ORDER BY
    lsy.years_since_first_term