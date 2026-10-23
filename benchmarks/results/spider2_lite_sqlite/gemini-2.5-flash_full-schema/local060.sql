WITH BaseSales AS (
  SELECT
    c.cust_city,
    t.calendar_quarter_desc,
    p.prod_id,
    p.prod_name,
    s.amount_sold
  FROM main.sales AS s
  JOIN main.customers AS c
    ON s.cust_id = c.cust_id
  JOIN main.countries AS co
    ON c.country_id = co.country_id
  JOIN main.times AS t
    ON s.time_id = t.time_id
  JOIN main.promotions AS pr
    ON s.promo_id = pr.promo_id
  JOIN main.products AS p
    ON s.prod_id = p.prod_id
  WHERE
    co.country_name = 'United States' AND t.calendar_quarter_desc IN ('2019-04', '2020-04') AND pr.promo_name = 'NO PROMOTION'
), CityQuarterSales AS (
  SELECT
    cust_city,
    calendar_quarter_desc AS quarter,
    SUM(amount_sold) AS total_city_sales
  FROM BaseSales
  GROUP BY
    cust_city,
    calendar_quarter_desc
), CityGrowth AS (
  SELECT
    cust_city
  FROM (
    SELECT
      cust_city,
      SUM(CASE WHEN quarter = '2019-04' THEN total_city_sales ELSE 0 END) AS sales_2019_q4,
      SUM(CASE WHEN quarter = '2020-04' THEN total_city_sales ELSE 0 END) AS sales_2020_q4
    FROM CityQuarterSales
    GROUP BY
      cust_city
  )
  WHERE
    sales_2019_q4 > 0 AND (sales_2020_q4 - sales_2019_q4) * 100.0 / sales_2019_q4 >= 20
), FilteredSales AS (
  SELECT
    bs.cust_city,
    bs.calendar_quarter_desc,
    bs.prod_id,
    bs.prod_name,
    bs.amount_sold
  FROM BaseSales AS bs
  JOIN CityGrowth AS cg
    ON bs.cust_city = cg.cust_city
), ProductOverallSales AS (
  SELECT
    prod_id,
    prod_name,
    SUM(amount_sold) AS overall_product_sales
  FROM FilteredSales
  GROUP BY
    prod_id,
    prod_name
), RankedProducts AS (
  SELECT
    prod_id,
    prod_name,
    overall_product_sales,
    NTILE(5) OVER (ORDER BY overall_product_sales DESC) AS ntile_group
  FROM ProductOverallSales
), TopProducts AS (
  SELECT
    prod_id,
    prod_name
  FROM RankedProducts
  WHERE
    ntile_group = 1
), ProductQuarterSales AS (
  SELECT
    tp.prod_id,
    tp.prod_name,
    fs.calendar_quarter_desc AS quarter,
    SUM(fs.amount_sold) AS product_sales_in_quarter
  FROM FilteredSales AS fs
  JOIN TopProducts AS tp
    ON fs.prod_id = tp.prod_id
  GROUP BY
    tp.prod_id,
    tp.prod_name,
    fs.calendar_quarter_desc
), TotalQuarterSales AS (
  SELECT
    calendar_quarter_desc AS quarter,
    SUM(amount_sold) AS total_sales_all_products_in_quarter
  FROM FilteredSales
  GROUP BY
    calendar_quarter_desc
), ProductShares AS (
  SELECT
    pqs.prod_name,
    SUM(CASE WHEN pqs.quarter = '2019-04' THEN pqs.product_sales_in_quarter ELSE 0 END) AS product_sales_2019_q4,
    SUM(CASE WHEN pqs.quarter = '2020-04' THEN pqs.product_sales_in_quarter ELSE 0 END) AS product_sales_2020_q4,
    MAX(CASE WHEN tqs.quarter = '2019-04' THEN tqs.total_sales_all_products_in_quarter ELSE 0 END) AS total_sales_2019_q4,
    MAX(CASE WHEN tqs.quarter = '2020-04' THEN tqs.total_sales_all_products_in_quarter ELSE 0 END) AS total_sales_2020_q4
  FROM ProductQuarterSales AS pqs
  JOIN TotalQuarterSales AS tqs
    ON pqs.quarter = tqs.quarter
  GROUP BY
    pqs.prod_name
)
SELECT
  prod_name,
  (product_sales_2020_q4 * 1.0 / total_sales_2020_q4) - (product_sales_2019_q4 * 1.0 / total_sales_2019_q4) AS share_change
FROM ProductShares
WHERE
  total_sales_2019_q4 > 0 AND total_sales_2020_q4 > 0
ORDER BY
  share_change DESC