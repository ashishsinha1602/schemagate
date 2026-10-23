WITH BaseSales AS (
    SELECT
        s.prod_id,
        c.cust_city,
        t.calendar_quarter_id,
        s.amount_sold
    FROM
        main.sales AS s
    JOIN
        main.times AS t ON s.time_id = t.time_id
    JOIN
        main.customers AS c ON s.cust_id = c.cust_id
    JOIN
        main.countries AS co ON c.country_id = co.country_id
    WHERE
        s.promo_id = 999
        AND co.country_name = 'United States'
        AND t.calendar_quarter_id IN (1772, 1776) -- Q4 2019 (1772) and Q4 2020 (1776)
),
CityQuarterSales AS (
    SELECT
        cust_city,
        calendar_quarter_id,
        SUM(amount_sold) AS total_city_sales
    FROM
        BaseSales
    GROUP BY
        cust_city,
        calendar_quarter_id
),
IncreasedSalesCities AS (
    SELECT
        cust_city
    FROM
        CityQuarterSales
    GROUP BY
        cust_city
    HAVING
        SUM(CASE WHEN calendar_quarter_id = 1776 THEN total_city_sales ELSE 0 END) >=
        SUM(CASE WHEN calendar_quarter_id = 1772 THEN total_city_sales ELSE 0 END) * 1.20
        AND SUM(CASE WHEN calendar_quarter_id = 1772 THEN total_city_sales ELSE 0 END) > 0
),
FilteredProductSales AS (
    SELECT
        bs.prod_id,
        bs.calendar_quarter_id,
        SUM(bs.amount_sold) AS product_quarter_sales
    FROM
        BaseSales AS bs
    JOIN
        IncreasedSalesCities AS isc ON bs.cust_city = isc.cust_city
    GROUP BY
        bs.prod_id,
        bs.calendar_quarter_id
),
TotalQuarterSales AS (
    SELECT
        calendar_quarter_id,
        SUM(product_quarter_sales) AS total_sales_all_products_quarter
    FROM
        FilteredProductSales
    GROUP BY
        calendar_quarter_id
),
ProductShare AS (
    SELECT
        fps.prod_id,
        fps.calendar_quarter_id,
        fps.product_quarter_sales,
        CAST(fps.product_quarter_sales AS REAL) / tqs.total_sales_all_products_quarter AS share_of_sales
    FROM
        FilteredProductSales AS fps
    JOIN
        TotalQuarterSales AS tqs ON fps.calendar_quarter_id = tqs.calendar_quarter_id
),
ProductShareComparison AS (
    SELECT
        prod_id,
        SUM(CASE WHEN calendar_quarter_id = 1772 THEN share_of_sales ELSE 0 END) AS share_q4_2019,
        SUM(CASE WHEN calendar_quarter_id = 1776 THEN share_of_sales ELSE 0 END) AS share_q4_2020,
        ABS(SUM(CASE WHEN calendar_quarter_id = 1776 THEN share_of_sales ELSE 0 END) -
            SUM(CASE WHEN calendar_quarter_id = 1772 THEN share_of_sales ELSE 0 END)) AS share_change_abs,
        SUM(product_quarter_sales) AS total_sales_combined
    FROM
        ProductShare
    GROUP BY
        prod_id
    HAVING
        SUM(product_quarter_sales) > 0 -- Ensure the product had sales in the filtered context
),
RankedProducts AS (
    SELECT
        prod_id,
        share_change_abs,
        NTILE(5) OVER (ORDER BY total_sales_combined DESC) AS sales_rank_group
    FROM
        ProductShareComparison
)
SELECT
    prod_id
FROM
    RankedProducts
WHERE
    sales_rank_group = 1
ORDER BY
    share_change_abs ASC
LIMIT 1