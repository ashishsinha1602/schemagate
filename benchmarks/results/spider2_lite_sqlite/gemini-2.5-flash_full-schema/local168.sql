WITH FilteredDataAnalystJobs AS (
  SELECT
    job_id,
    salary_year_avg
  FROM main.job_postings_fact
  WHERE
    job_title_short = 'Data Analyst' AND job_work_from_home = 1 AND salary_year_avg IS NOT NULL
), TopSkills AS (
  SELECT
    sd.skills
  FROM FilteredDataAnalystJobs AS fdaj
  JOIN main.skills_job_dim AS sjd
    ON fdaj.job_id = sjd.job_id
  JOIN main.skills_dim AS sd
    ON sjd.skill_id = sd.skill_id
  GROUP BY
    sd.skills
  ORDER BY
    COUNT(fdaj.job_id) DESC
  LIMIT 3
)
SELECT
  AVG(fdaj.salary_year_avg)
FROM FilteredDataAnalystJobs AS fdaj
JOIN main.skills_job_dim AS sjd
  ON fdaj.job_id = sjd.job_id
JOIN main.skills_dim AS sd
  ON sjd.skill_id = sd.skill_id
WHERE
  sd.skills IN (
    SELECT
      skills
    FROM TopSkills
  )