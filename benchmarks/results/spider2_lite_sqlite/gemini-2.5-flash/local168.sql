WITH FilteredDataAnalystJobs AS (
    SELECT
        job_id,
        salary_year_avg
    FROM
        main.job_postings_fact
    WHERE
        job_title_short = 'Data Analyst'
        AND salary_year_avg IS NOT NULL
        AND job_work_from_home = 1
),
Top3Skills AS (
    SELECT
        sjd.skill_id
    FROM
        FilteredDataAnalystJobs fdaj
    JOIN
        main.skills_job_dim sjd ON fdaj.job_id = sjd.job_id
    GROUP BY
        sjd.skill_id
    ORDER BY
        COUNT(sjd.skill_id) DESC
    LIMIT 3
)
SELECT
    AVG(fdaj.salary_year_avg)
FROM
    FilteredDataAnalystJobs fdaj
JOIN
    main.skills_job_dim sjd ON fdaj.job_id = sjd.job_id
WHERE
    sjd.skill_id IN (SELECT skill_id FROM Top3Skills)