WITH AnnualSales AS (
    SELECT
        s.businessentityid,
        STRFTIME('%Y', soh.orderdate) AS sales_year,
        SUM(soh.subtotal) AS total_sales
    FROM
        main.salesperson AS s
    JOIN
        main.salesorderheader AS soh
        ON s.businessentityid = soh.salespersonid
    GROUP BY
        s.businessentityid,
        sales_year
),
AnnualQuota AS (
    SELECT
        spqh.BusinessEntityID,
        STRFTIME('%Y', spqh.QuotaDate) AS quota_year,
        SUM(spqh.SalesQuota) AS total_quota
    FROM
        main.SalesPersonQuotaHistory AS spqh
    GROUP BY
        spqh.BusinessEntityID,
        quota_year
)
SELECT
    COALESCE(sa.businessentityid, aq.BusinessEntityID) AS salesperson_id,
    COALESCE(sa.sales_year, aq.quota_year) AS year,
    COALESCE(sa.total_sales, 0) - COALESCE(aq.total_quota, 0) AS sales_quota_difference
FROM
    AnnualSales AS sa
LEFT JOIN
    AnnualQuota AS aq
    ON sa.businessentityid = aq.BusinessEntityID AND sa.sales_year = aq.quota_year

UNION ALL

SELECT
    aq.BusinessEntityID AS salesperson_id,
    aq.quota_year AS year,
    COALESCE(sa.total_sales, 0) - COALESCE(aq.total_quota, 0) AS sales_quota_difference
FROM
    AnnualQuota AS aq
LEFT JOIN
    AnnualSales AS sa
    ON sa.businessentityid = aq.BusinessEntityID AND sa.sales_year = aq.quota_year
WHERE
    sa.businessentityid IS NULL
ORDER BY
    salesperson_id,
    year