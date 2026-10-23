WITH france_sales_filtered AS (
  SELECT
    s.prod_id,
    t.calendar_year,
    t.calendar_month_number,
    t.calendar_month_name,
    s.amount_sold
  FROM main.sales AS s
  JOIN main.times AS t
    ON s.time_id = t.time_id
  JOIN main.customers AS c
    ON s.cust_id = c.cust_id
  JOIN main.countries AS co
    ON c.country_id = co.country_id
  JOIN main.promotions AS p
    ON s.promo_id = p.promo_id
  JOIN main.channels AS ch
    ON s.channel_id = ch.channel_id
  WHERE
    co.country_name = 'France' AND t.calendar_year IN (2019, 2020) AND p.promo_total_id = 1 AND ch.channel_total_id = 1
), monthly_product_sales AS (
  SELECT
    prod_id,
    calendar_year,
    calendar_month_number,
    calendar_month_name,
    SUM(amount_sold) AS total_monthly_sales
  FROM france_sales_filtered
  GROUP BY
    prod_id,
    calendar_year,
    calendar_month_number,
    calendar_month_name
), sales_2019_2020 AS (
  SELECT
    prod_id,
    calendar_month_number,
    calendar_month_name,
    SUM(CASE WHEN calendar_year = 2019 THEN total_monthly_sales ELSE 0 END) AS sales_2019,
    SUM(CASE WHEN calendar_year = 2020 THEN total_monthly_sales ELSE 0 END) AS sales_2020
  FROM monthly_product_sales
  GROUP BY
    prod_id,
    calendar_month_number,
    calendar_month_name
), projected_2021_sales AS (
  SELECT
    prod_id,
    calendar_month_number,
    calendar_month_name,
    CASE
      WHEN sales_2019 = 0 THEN sales_2020 -- If no sales in 2019, project 2020 sales for 2021
      ELSE (sales_2020 * sales_2020 * 1.0) / sales_2019
    END AS projected_sales_2021
  FROM sales_2019_2020
), projected_2021_usd AS (
  SELECT
    p21s.calendar_month_number,
    p21s.calendar_month_name,
    SUM(p21s.projected_sales_2021 * cur.to_us) AS projected_sales_usd_for_month
  FROM projected_2021_sales AS p21s
  JOIN main.currency AS cur
    ON cur.country = 'France' AND cur.year = 2021 AND cur.month = p21s.calendar_month_number
  GROUP BY
    p21s.calendar_month_number,
    p21s.calendar_month_name
), ranked_monthly_sales AS (
  SELECT
    projected_sales_usd_for_month,
    ROW_NUMBER() OVER (ORDER BY projected_sales_usd_for_month) AS rn,
    COUNT(*) OVER () AS total_rows
  FROM projected_2021_usd
)
SELECT
  AVG(projected_sales_usd_for_month)
FROM ranked_monthly_sales
WHERE
  rn = (total_rows + 1) / 2 OR rn = (total_rows + 2) / 2