WITH CountriesWithManyCustomers AS (
  SELECT
    c.Country
  FROM main.customers AS c
  GROUP BY
    c.Country
  HAVING
    COUNT(c.CustomerId) > 4
), FilteredSales AS (
  SELECT
    i.Total
  FROM main.invoices AS i
  JOIN main.customers AS c
    ON i.CustomerId = c.CustomerId
  WHERE
    c.Country IN (
      SELECT
        Country
      FROM CountriesWithManyCustomers
    )
), RankedSales AS (
  SELECT
    Total,
    ROW_NUMBER() OVER (ORDER BY Total) AS rn,
    COUNT(*) OVER () AS total_count
  FROM FilteredSales
)
SELECT
  AVG(Total)
FROM RankedSales
WHERE
  rn IN ((total_count + 1) / 2, (total_count + 2) / 2)