WITH US_Q4_Sales_NoPromo AS (
    SELECT
        c.cust_city,
        t.calendar_year,
        SUM(s.amount_sold) AS total_city_sales
    FROM main.sales AS s
    JOIN main.customers AS c
        ON s.cust_id = c.cust_id
    JOIN main.times AS t
        ON s.time_id = t.time_id
    JOIN main.promotions AS p
        ON s.promo_id = p.promo_id
    JOIN main.countries AS co
        ON c.country_id = co.country_id
    WHERE
        co.country_name = 'United States' AND
        t.calendar_quarter_number = 4 AND
        t.calendar_year IN (2019, 2020) AND
        p.promo_subcategory = 'NO PROMOTION'
    GROUP BY
        c.cust_city,
        t.calendar_year
),
EligibleCities AS (
    SELECT
        s2019.cust_city
    FROM US_Q4_Sales_NoPromo AS s2019
    JOIN US_Q4_Sales_NoPromo AS s2020
        ON s2019.cust_city = s2020.cust_city
    WHERE
        s2019.calendar_year = 2019 AND
        s2020.calendar_year = 2020 AND
        s2020.total_city_sales >= s2019.total_city_sales * 1.20
),
ProductSalesInEligibleCities AS (
    SELECT
        p.prod_id,
        p.prod_name,
        SUM(s.amount_sold) AS total_product_sales_overall
    FROM main.sales AS s
    JOIN main.products AS p
        ON s.prod_id = p.prod_id
    JOIN main.customers AS c
        ON s.cust_id = c.cust_id
    JOIN main.times AS t
        ON s.time_id = t.time_id
    JOIN main.promotions AS pr
        ON s.promo_id = pr.promo_id
    WHERE
        c.cust_city IN (SELECT cust_city FROM EligibleCities) AND
        t.calendar_quarter_number = 4 AND
        t.calendar_year IN (2019, 2020) AND
        pr.promo_subcategory = 'NO PROMOTION'
    GROUP BY
        p.prod_id,
        p.prod_name
),
RankedProducts AS (
    SELECT
        prod_id,
        prod_name,
        total_product_sales_overall,
        NTILE(5) OVER (ORDER BY total_product_sales_overall DESC) AS sales_ntile
    FROM ProductSalesInEligibleCities
),
Top20PercentProducts AS (
    SELECT
        prod_id,
        prod_name
    FROM RankedProducts
    WHERE sales_ntile = 1
),
ProductSalesByYear AS (
    SELECT
        tp.prod_id,
        tp.prod_name,
        t.calendar_year,
        SUM(s.amount_sold) AS product_sales_year
    FROM main.sales AS s
    JOIN main.products AS prd
        ON s.prod_id = prd.prod_id
    JOIN main.customers AS c
        ON s.cust_id = c.cust_id
    JOIN main.times AS t
        ON s.time_id = t.time_id
    JOIN main.promotions AS pr
        ON s.promo_id = pr.promo_id
    JOIN Top20PercentProducts AS tp
        ON prd.prod_id = tp.prod_id
    WHERE
        c.cust_city IN (SELECT cust_city FROM EligibleCities) AND
        t.calendar_quarter_number = 4 AND
        t.calendar_year IN (2019, 2020) AND
        pr.promo_subcategory = 'NO PROMOTION'
    GROUP BY
        tp.prod_id,
        tp.prod_name,
        t.calendar_year
),
TotalSalesByYear AS (
    SELECT
        t.calendar_year,
        SUM(s.amount_sold) AS total_sales_all_products_year
    FROM main.sales AS s
    JOIN main.customers AS c
        ON s.cust_id = c.cust_id
    JOIN main.times AS t
        ON s.time_id = t.time_id
    JOIN main.promotions AS pr
        ON s.promo_id = pr.promo_id
    WHERE
        c.cust_city IN (SELECT cust_city FROM EligibleCities) AND
        t.calendar_quarter_number = 4 AND
        t.calendar_year IN (2019, 2020) AND
        pr.promo_subcategory = 'NO PROMOTION'
    GROUP BY
        t.calendar_year
),
ProductShares AS (
    SELECT
        psy.prod_id,
        psy.prod_name,
        psy.calendar_year,
        CAST(psy.product_sales_year AS REAL) / tsy.total_sales_all_products_year AS sales_share
    FROM ProductSalesByYear AS psy
    JOIN TotalSalesByYear AS tsy
        ON psy.calendar_year = tsy.calendar_year
),
ShareComparison AS (
    SELECT
        s2019.prod_id,
        s2019.prod_name,
        s2019.sales_share AS share_2019,
        s2020.sales_share AS share_2020,
        s2020.sales_share - s2019.sales_share AS share_change
    FROM ProductShares AS s2019
    JOIN ProductShares AS s2020
        ON s2019.prod_id = s2020.prod_id
    WHERE
        s2019.calendar_year = 2019 AND
        s2020.calendar_year = 2020
)
SELECT
    prod_name,
    share_2019,
    share_2020,
    share_change
FROM ShareComparison
ORDER BY
    share_change DESC