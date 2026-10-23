WITH CountryCustomerCounts AS (
  SELECT
    c.Country
  FROM main.customers AS c
  GROUP BY
    c.Country
  HAVING
    COUNT(c.CustomerId) > 4
), SalesInEligibleCountries AS (
  SELECT
    i.Total
  FROM main.invoices AS i
  JOIN main.customers AS c
    ON i.CustomerId = c.CustomerId
  WHERE
    c.Country IN (
      SELECT
        Country
      FROM CountryCustomerCounts
    )
), RankedSales AS (
  SELECT
    Total,
    ROW_NUMBER() OVER (ORDER BY Total) AS rn,
    COUNT(*) OVER () AS total_rows
  FROM SalesInEligibleCountries
)
SELECT
  CASE
    WHEN total_rows % 2 = 1
    THEN (
      SELECT
        Total
      FROM RankedSales
      WHERE
        rn = (total_rows + 1) / 2
    )
    ELSE (
      (
        SELECT
          Total
        FROM RankedSales
        WHERE
          rn = total_rows / 2
      ) + (
        SELECT
          Total
        FROM RankedSales
        WHERE
          rn = (total_rows / 2) + 1
      )
    ) / 2.0
  END
FROM RankedSales
LIMIT 1