WITH cleaned AS (
  SELECT CompanyName, Location,
         CAST(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(Salary, '₹', ''), ',', ''), '/yr', ''), '/mo', ''), '/hr', '') AS REAL) AS sal
  FROM SalaryDataset
),
nat AS (
  SELECT AVG(sal) AS country_avg FROM cleaned
),
city AS (
  SELECT Location, CompanyName, AVG(sal) AS state_avg
  FROM cleaned
  WHERE Location IN ('Mumbai', 'Pune', 'New Delhi', 'Hyderabad')
  GROUP BY Location, CompanyName
),
ranked AS (
  SELECT Location, CompanyName, state_avg,
         ROW_NUMBER() OVER (PARTITION BY Location ORDER BY state_avg DESC) AS rn
  FROM city
)
SELECT r.Location AS Location,
       r.CompanyName AS "Company Name",
       r.state_avg AS "Average Salary in State",
       n.country_avg AS "Average Salary in Country"
FROM ranked r
CROSS JOIN nat n
WHERE r.rn <= 5
ORDER BY r.Location, r.state_avg DESC