WITH base AS (
  SELECT job_id, salary_year_avg
  FROM job_postings_fact
  WHERE job_title_short = 'Data Analyst'
    AND salary_year_avg IS NOT NULL
    AND job_work_from_home = 1
),
top_skills AS (
  SELECT s.skill_id, COUNT(*) AS cnt
  FROM base b
  JOIN skills_job_dim s ON s.job_id = b.job_id
  GROUP BY s.skill_id
  ORDER BY cnt DESC, s.skill_id
  LIMIT 3
)
SELECT AVG(b.salary_year_avg) AS avg_salary
FROM base b
JOIN skills_job_dim s ON s.job_id = b.job_id
JOIN top_skills t ON t.skill_id = s.skill_id