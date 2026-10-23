WITH FemaleLegislators AS (
    SELECT
        l.id_bioguide
    FROM
        main.legislators AS l
    WHERE
        l.gender = 'F'
),
LegislatorsWithDec31Terms AS (
    SELECT DISTINCT
        lt.id_bioguide
    FROM
        main.legislators_terms AS lt
    WHERE
        (substr(lt.term_start, 1, 4) < substr(lt.term_end, 1, 4))
        OR
        (
            substr(lt.term_start, 1, 4) = substr(lt.term_end, 1, 4)
            AND lt.term_start <= substr(lt.term_start, 1, 4) || '-12-31'
            AND lt.term_end >= substr(lt.term_start, 1, 4) || '-12-31'
        )
),
EligibleFemaleLegislators AS (
    SELECT
        fl.id_bioguide
    FROM
        FemaleLegislators AS fl
    JOIN
        LegislatorsWithDec31Terms AS ldt
    ON
        fl.id_bioguide = ldt.id_bioguide
),
LegislatorFirstTermState AS (
    SELECT
        lt.id_bioguide,
        lt.state,
        ROW_NUMBER() OVER (PARTITION BY lt.id_bioguide ORDER BY lt.term_start ASC) AS rn
    FROM
        main.legislators_terms AS lt
)
SELECT
    lfts.state,
    COUNT(efl.id_bioguide) AS female_legislator_count
FROM
    EligibleFemaleLegislators AS efl
JOIN
    LegislatorFirstTermState AS lfts
ON
    efl.id_bioguide = lfts.id_bioguide
WHERE
    lfts.rn = 1
GROUP BY
    lfts.state
ORDER BY
    female_legislator_count DESC
LIMIT 1