WITH US_Sales_Q4 AS (
    SELECT
        s.prod_id,
        p.prod_name,
        c.cust_city,
        t.calendar_quarter_id,
        s.amount_sold
    FROM
        main.sales AS s
    JOIN
        main.times AS t
        ON s.time_id = t.time_id
    JOIN
        main.customers AS c
        ON s.cust_id = c.cust_id
    JOIN
        main.countries AS co
        ON c.country_id = co.country_id
    JOIN
        main.products AS p
        ON s.prod_id = p.prod_id
    WHERE
        s.promo_id = 999
        AND co.country_name = 'United States'
        AND t.calendar_quarter_id IN (1772, 1776)
),
City_Quarter_Sales AS (
    SELECT
        cust_city,
        calendar_quarter_id,
        SUM(amount_sold) AS total_city_sales
    FROM
        US_Sales_Q4
    GROUP BY
        cust_city,
        calendar_quarter_id
),
City_Sales_Comparison AS (
    SELECT
        cust_city,
        SUM(CASE WHEN calendar_quarter_id = 1772 THEN total_city_sales ELSE 0 END) AS sales_q4_2019,
        SUM(CASE WHEN calendar_quarter_id = 1776 THEN total_city_sales ELSE 0 END) AS sales_q4_2020
    FROM
        City_Quarter_Sales
    GROUP BY
        cust_city
),
Increasing_Cities AS (
    SELECT
        cust_city
    FROM
        City_Sales_Comparison
    WHERE
        sales_q4_2019 > 0 -- Ensure there were sales in Q4 2019 to calculate increase
        AND (sales_q4_2020 - sales_q4_2019) * 1.0 / sales_q4_2019 >= 0.20
),
Filtered_Product_Sales AS (
    SELECT
        usq.prod_id,
        usq.prod_name,
        usq.calendar_quarter_id,
        SUM(usq.amount_sold) AS product_sales
    FROM
        US_Sales_Q4 AS usq
    JOIN
        Increasing_Cities AS ic
        ON usq.cust_city = ic.cust_city
    GROUP BY
        usq.prod_id,
        usq.prod_name,
        usq.calendar_quarter_id
),
Quarter_Total_Sales AS (
    SELECT
        calendar_quarter_id,
        SUM(product_sales) AS total_quarter_sales
    FROM
        Filtered_Product_Sales
    GROUP BY
        calendar_quarter_id
),
Product_Share AS (
    SELECT
        fps.prod_id,
        fps.prod_name,
        fps.calendar_quarter_id,
        fps.product_sales,
        qts.total_quarter_sales,
        (fps.product_sales * 1.0 / qts.total_quarter_sales) AS share
    FROM
        Filtered_Product_Sales AS fps
    JOIN
        Quarter_Total_Sales AS qts
        ON fps.calendar_quarter_id = qts.calendar_quarter_id
),
Product_Sales_Across_Quarters AS (
    SELECT
        prod_id,
        prod_name,
        SUM(product_sales) AS total_product_sales_filtered_cities
    FROM
        Filtered_Product_Sales
    GROUP BY
        prod_id,
        prod_name
),
Ranked_Products AS (
    SELECT
        prod_id,
        prod_name,
        total_product_sales_filtered_cities,
        NTILE(5) OVER (ORDER BY total_product_sales_filtered_cities DESC) AS sales_ntile
    FROM
        Product_Sales_Across_Quarters
),
Top_20_Percent_Products AS (
    SELECT
        prod_id,
        prod_name
    FROM
        Ranked_Products
    WHERE
        sales_ntile = 1
),
Product_Share_Pivoted AS (
    SELECT
        ps.prod_id,
        ps.prod_name,
        SUM(CASE WHEN ps.calendar_quarter_id = 1772 THEN ps.share ELSE 0 END) AS share_q4_2019,
        SUM(CASE WHEN ps.calendar_quarter_id = 1776 THEN ps.share ELSE 0 END) AS share_q4_2020
    FROM
        Product_Share AS ps
    GROUP BY
        ps.prod_id,
        ps.prod_name
)
SELECT
    t20.prod_name
FROM
    Top_20_Percent_Products AS t20
JOIN
    Product_Share_Pivoted AS psp
    ON t20.prod_id = psp.prod_id
ORDER BY
    ABS(psp.share_q4_2020 - psp.share_q4_2019) ASC
LIMIT 1