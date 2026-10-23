WITH BaseCleanedSalaries AS (
    SELECT
        CompanyName,
        Location,
        -- Remove common non-numeric characters and spaces from the salary string
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(Salary, '$', ''), ',', ''), 'Rs.', ''), 'p.a.', ''), 'per annum', ''), ' ', '') AS BaseSalaryString
    FROM main.SalaryDataset
),
CleanedSalaries AS (
    SELECT
        CompanyName,
        Location,
        -- Convert the cleaned salary string to a numeric value, handling 'k' (thousands) and 'L' (lakhs) multipliers
        CASE
            WHEN BaseSalaryString LIKE '%k' OR BaseSalaryString LIKE '%K' THEN
                CAST(REPLACE(REPLACE(BaseSalaryString, 'k', ''), 'K', '') AS REAL) * 1000
            WHEN BaseSalaryString LIKE '%L' OR BaseSalaryString LIKE '%l' THEN
                CAST(REPLACE(REPLACE(BaseSalaryString, 'L', ''), 'l', '') AS REAL) * 100000
            ELSE
                CAST(BaseSalaryString AS REAL)
        END AS CleanedSalary
    FROM BaseCleanedSalaries
    -- Filter out any entries that might result in NULL or empty strings after initial cleaning,
    -- which would cause issues with CAST or lead to incorrect calculations.
    WHERE BaseSalaryString IS NOT NULL AND BaseSalaryString != ''
),
NationalAverage AS (
    -- Calculate the overall national average salary from all cleaned salaries
    SELECT AVG(CleanedSalary) AS OverallAvgSalary
    FROM CleanedSalaries
),
CityCompanyAverages AS (
    -- Calculate the average salary for each company within the specified cities
    SELECT
        Location,
        CompanyName,
        AVG(CleanedSalary) AS CompanyAvgSalaryInCity
    FROM CleanedSalaries
    WHERE Location IN ('Mumbai', 'Pune', 'New Delhi', 'Hyderabad')
    GROUP BY Location, CompanyName
),
RankedCompanyAverages AS (
    -- Rank companies within each specified city based on their average salary
    SELECT
        Location,
        CompanyName,
        CompanyAvgSalaryInCity,
        RANK() OVER (PARTITION BY Location ORDER BY CompanyAvgSalaryInCity DESC) AS RankNo
    FROM CityCompanyAverages
)
-- Final selection: display location, company name, city average salary, and national average salary
-- for the top 5 companies in each specified city.
SELECT
    RCA.Location,
    RCA.CompanyName,
    RCA.CompanyAvgSalaryInCity AS "Average Salary in State", -- Renamed as per prompt
    NA.OverallAvgSalary AS "Average Salary in Country"
FROM RankedCompanyAverages AS RCA
CROSS JOIN NationalAverage AS NA
WHERE RCA.RankNo <= 5
ORDER BY RCA.Location, RCA.RankNo