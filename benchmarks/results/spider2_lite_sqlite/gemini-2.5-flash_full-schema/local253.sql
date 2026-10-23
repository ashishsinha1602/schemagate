WITH CleanedAllSalaries AS (
    SELECT
        CompanyName,
        Location,
        CAST(REPLACE(REPLACE(REPLACE(Salary, '$', ''), '₹', ''), ',', '') AS REAL) AS CleanedSalaryValue
    FROM
        main.SalaryDataset
    WHERE
        Salary IS NOT NULL
        AND Salary GLOB '*[0-9]*'
),
NationalAverage AS (
    SELECT
        AVG(CleanedSalaryValue) AS OverallNationalAverageSalary
    FROM
        CleanedAllSalaries
),
CityCompanyAvg AS (
    SELECT
        Location,
        CompanyName,
        AVG(CleanedSalaryValue) AS AverageSalaryInCity
    FROM
        CleanedAllSalaries
    WHERE
        Location IN ('Mumbai', 'Pune', 'New Delhi', 'Hyderabad')
    GROUP BY
        Location,
        CompanyName
),
RankedCityCompanyAvg AS (
    SELECT
        Location,
        CompanyName,
        AverageSalaryInCity,
        RANK() OVER (PARTITION BY Location ORDER BY AverageSalaryInCity DESC) AS RankWithinCity
    FROM
        CityCompanyAvg
)
SELECT
    R.Location,
    R.CompanyName AS "Company Name",
    R.AverageSalaryInCity AS "Average Salary in State",
    NA.OverallNationalAverageSalary AS "Average Salary in Country"
FROM
    RankedCityCompanyAvg AS R
CROSS JOIN
    NationalAverage AS NA
WHERE
    R.RankWithinCity <= 5
ORDER BY
    R.Location,
    R.AverageSalaryInCity DESC