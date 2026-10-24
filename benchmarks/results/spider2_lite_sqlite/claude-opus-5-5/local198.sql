WITH country_customers AS (
  SELECT Country
  FROM customers
  GROUP BY Country
  HAVING COUNT(*) > 4
),
country_sales AS (
  SELECT c.Country, SUM(i.Total) AS total_sales
  FROM invoices i
  JOIN customers c ON c.CustomerId = i.CustomerId
  WHERE c.Country IN (SELECT Country FROM country_customers)
  GROUP BY c.Country
),
ranked AS (
  SELECT total_sales,
         ROW_NUMBER() OVER (ORDER BY total_sales) AS rn,
         COUNT(*) OVER () AS cnt
  FROM country_sales
)
SELECT AVG(total_sales) AS median_total_sales
FROM ranked
WHERE rn IN ((cnt + 1) / 2, (cnt + 2) / 2)