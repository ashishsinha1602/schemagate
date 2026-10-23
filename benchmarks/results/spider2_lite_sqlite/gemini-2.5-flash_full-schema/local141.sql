WITH AnnualSales AS (
    SELECT
        salespersonid AS BusinessEntityID,
        STRFTIME('%Y', orderdate) AS sales_year,
        SUM(totaldue) AS annual_sales
    FROM
        main.salesorderheader
    WHERE
        salespersonid IS NOT NULL
    GROUP BY
        salespersonid,
        sales_year
),
AnnualQuotas AS (
    WITH RankedQuotas AS (
        SELECT
            BusinessEntityID,
            STRFTIME('%Y', QuotaDate) AS quota_year,
            SalesQuota,
            ROW_NUMBER() OVER (PARTITION BY BusinessEntityID, STRFTIME('%Y', QuotaDate) ORDER BY QuotaDate DESC) AS rn
        FROM
            main.SalesPersonQuotaHistory
    )
    SELECT
        BusinessEntityID,
        quota_year,
        SalesQuota AS annual_quota
    FROM
        RankedQuotas
    WHERE
        rn = 1
)
SELECT
    COALESCE(ASales.BusinessEntityID, AQuotas.BusinessEntityID) AS salesperson_id,
    COALESCE(ASales.sales_year, AQuotas.quota_year) AS sales_year,
    COALESCE(ASales.annual_sales, 0) AS total_sales,
    COALESCE(AQuotas.annual_quota, 0) AS annual_quota,
    (COALESCE(ASales.annual_sales, 0) - COALESCE(AQuotas.annual_quota, 0)) AS sales_vs_quota_difference
FROM
    AnnualSales AS ASales
LEFT JOIN
    AnnualQuotas AS AQuotas
ON
    ASales.BusinessEntityID = AQuotas.BusinessEntityID AND ASales.sales_year = AQuotas.quota_year

UNION ALL

SELECT
    AQuotas.BusinessEntityID AS salesperson_id,
    AQuotas.quota_year AS sales_year,
    COALESCE(ASales.annual_sales, 0) AS total_sales,
    COALESCE(AQuotas.annual_quota, 0) AS annual_quota,
    (COALESCE(ASales.annual_sales, 0) - COALESCE(AQuotas.annual_quota, 0)) AS sales_vs_quota_difference
FROM
    AnnualQuotas AS AQuotas
LEFT JOIN
    AnnualSales AS ASales
ON
    ASales.BusinessEntityID = AQuotas.BusinessEntityID AND ASales.sales_year = AQuotas.quota_year
WHERE
    ASales.BusinessEntityID IS NULL
ORDER BY
    salesperson_id,
    sales_year