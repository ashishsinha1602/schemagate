WITH filtered AS (
  SELECT job_id, salary_year_avg
  FROM job_postings_fact
  WHERE job_title_short = 'Data Analyst'
    AND salary_year_avg IS NOT NULL
    AND job_work_from_home = 1
),
top_skills AS (
  SELECT sj.skill_id
  FROM filtered f
  JOIN skills_job_dim sj ON sj.job_id = f.job_id
  GROUP BY sj.skill_id
  ORDER BY COUNT(*) DESC
  LIMIT 3
),
skill_avg AS (
  SELECT sj.skill_id, AVG(f.salary_year_avg) AS avg_salary
  FROM filtered f
  JOIN skills_job_dim sj ON sj.job_id = f.job_id
  WHERE sj.skill_id IN (SELECT skill_id FROM top_skills)
  GROUP BY sj.skill_id
)
SELECT AVG(avg_salary) AS overall_avg_salary
FROM skill_avg