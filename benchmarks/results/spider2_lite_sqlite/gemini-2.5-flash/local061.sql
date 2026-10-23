WITH france_sales_filtered AS (
  SELECT
    s.prod_id,
    t.calendar_year,
    t.calendar_month_number,
    t.calendar_month_desc,
    s.amount_sold
  FROM main.sales AS s
  JOIN main.customers AS c
    ON s.cust_id = c.cust_id
  JOIN main.countries AS co
    ON c.country_id = co.country_id
  JOIN main.promotions AS p
    ON s.promo_id = p.promo_id
  JOIN main.channels AS ch
    ON s.channel_id = ch.channel_id
  JOIN main.times AS t
    ON s.time_id = t.time_id
  WHERE
    co.country_name = 'France' AND p.promo_total_id = 1 AND ch.channel_total_id = 1 AND t.calendar_year IN (2019, 2020)
), monthly_product_sales AS (
  SELECT
    prod_id,
    calendar_year,
    calendar_month_number,
    calendar_month_desc,
    SUM(amount_sold) AS total_sales
  FROM france_sales_filtered
  GROUP BY
    prod_id,
    calendar_year,
    calendar_month_number,
    calendar_month_desc
), sales_2019_2020 AS (
  SELECT
    mps.prod_id,
    mps.calendar_month_number,
    mps.calendar_month_desc,
    COALESCE(MAX(CASE WHEN mps.calendar_year = 2019 THEN mps.total_sales END), 0.0) AS sales_2019,
    COALESCE(MAX(CASE WHEN mps.calendar_year = 2020 THEN mps.total_sales END), 0.0) AS sales_2020
  FROM monthly_product_sales AS mps
  GROUP BY
    mps.prod_id,
    mps.calendar_month_number,
    mps.calendar_month_desc
), projected_2021_sales AS (
  SELECT
    s.prod_id,
    s.calendar_month_number,
    s.calendar_month_desc,
    CASE
      WHEN s.sales_2019 = 0 THEN s.sales_2020
      ELSE (s.sales_2020 * s.sales_2020) / s.sales_2019
    END AS projected_sales_2021
  FROM sales_2019_2020 AS s
), projected_2021_sales_usd AS (
  SELECT
    p.calendar_month_number,
    p.calendar_month_desc,
    p.projected_sales_2021 * COALESCE(cu.to_us, 1.0) AS projected_sales_usd
  FROM projected_2021_sales AS p
  LEFT JOIN main.currency AS cu
    ON cu.year = 2021 AND cu.month = p.calendar_month_number AND cu.country = 'France'
)
SELECT
  p_usd.calendar_month_desc,
  ROUND(AVG(p_usd.projected_sales_usd), 2) AS average_projected_monthly_sales_usd
FROM projected_2021_sales_usd AS p_usd
GROUP BY
  p_usd.calendar_month_number,
  p_usd.calendar_month_desc
ORDER BY
  p_usd.calendar_month_number