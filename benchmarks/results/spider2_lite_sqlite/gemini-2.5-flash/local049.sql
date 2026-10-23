WITH unicorn_companies_data AS (
    SELECT
        cf.company_id,
        ci.industry,
        STRFTIME('%Y', cd.date_joined) AS join_year
    FROM
        main.companies_funding AS cf
    JOIN
        main.companies_dates AS cd
        ON cf.company_id = cd.company_id
    JOIN
        main.companies_industries AS ci
        ON cf.company_id = ci.company_id
    WHERE
        cf.valuation >= 1000000000
        AND STRFTIME('%Y', cd.date_joined) BETWEEN '2019' AND '2021'
), top_industry_identification AS (
    SELECT
        industry
    FROM
        unicorn_companies_data
    GROUP BY
        industry
    ORDER BY
        COUNT(company_id) DESC
    LIMIT 1
), yearly_unicorn_counts_in_top_industry AS (
    SELECT
        ucd.join_year,
        COUNT(ucd.company_id) AS num_unicorns
    FROM
        unicorn_companies_data AS ucd
    JOIN
        top_industry_identification AS ti
        ON ucd.industry = ti.industry
    GROUP BY
        ucd.join_year
)
SELECT
    AVG(num_unicorns)
FROM
    yearly_unicorn_counts_in_top_industry