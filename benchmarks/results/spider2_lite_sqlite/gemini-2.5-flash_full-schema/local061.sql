WITH france_sales_history AS (
  SELECT
    s.prod_id,
    t.calendar_month_number,
    t.calendar_month_desc,
    t.calendar_year,
    SUM(s.amount_sold) AS total_amount_sold
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
    co.country_name = 'France' AND p.promo_total_id = 1 AND ch.channel_total_id = 1 AND t.calendar_year IN (2019, 2020)
  GROUP BY
    s.prod_id,
    t.calendar_month_number,
    t.calendar_month_desc,
    t.calendar_year
), monthly_product_sales AS (
  SELECT
    prod_id,
    calendar_month_number,
    calendar_month_desc,
    SUM(CASE WHEN calendar_year = 2019 THEN total_amount_sold ELSE 0 END) AS sales_2019,
    SUM(CASE WHEN calendar_year = 2020 THEN total_amount_sold ELSE 0 END) AS sales_2020
  FROM france_sales_history
  GROUP BY
    prod_id,
    calendar_month_number,
    calendar_month_desc
), projected_2021_sales AS (
  SELECT
    prod_id,
    calendar_month_number,
    calendar_month_desc,
    CASE
      WHEN sales_2019 = 0 THEN sales_2020
      ELSE (sales_2020 * sales_2020) / sales_2019
    END AS projected_sales_2021
  FROM monthly_product_sales
), projected_2021_usd AS (
  SELECT
    p.calendar_month_number,
    p.calendar_month_desc,
    p.projected_sales_2021 * COALESCE(cu.to_us, 1) AS projected_sales_usd
  FROM projected_2021_sales AS p
  LEFT JOIN main.currency AS cu
    ON p.calendar_month_number = cu.month AND cu.year = 2021
)
SELECT
  calendar_month_desc,
  ROUND(AVG(projected_sales_usd), 2) AS average_projected_monthly_sales_usd
FROM projected_2021_usd
GROUP BY
  calendar_month_number,
  calendar_month_desc
ORDER BY
  calendar_month_number