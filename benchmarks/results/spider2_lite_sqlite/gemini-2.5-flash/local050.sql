WITH france_sales_2019_2020 AS (
  SELECT
    t.calendar_year,
    t.calendar_month_number,
    s.prod_id,
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
    co.country_name = 'France' AND t.calendar_year IN (2019, 2020) AND p.promo_total_id = 1 AND ch.channel_total_id = 1
  GROUP BY
    t.calendar_year,
    t.calendar_month_number,
    s.prod_id
), pivoted_sales AS (
  SELECT
    calendar_month_number,
    prod_id,
    SUM(CASE WHEN calendar_year = 2019 THEN total_amount_sold ELSE 0 END) AS sales_2019,
    SUM(CASE WHEN calendar_year = 2020 THEN total_amount_sold ELSE 0 END) AS sales_2020
  FROM france_sales_2019_2020
  GROUP BY
    calendar_month_number,
    prod_id
), projected_sales_2021 AS (
  SELECT
    calendar_month_number,
    prod_id,
    CASE
      WHEN sales_2019 = 0 AND sales_2020 = 0 THEN 0.0
      WHEN sales_2019 = 0 AND sales_2020 > 0 THEN sales_2020 -- If no sales in 2019 but sales in 2020, project 2020 sales
      WHEN sales_2019 > 0 AND sales_2020 = 0 THEN 0.0 -- If sales in 2019 but none in 2020, project 0
      WHEN sales_2019 > 0 AND sales_2020 > 0 THEN (sales_2020 * sales_2020) / sales_2019
      ELSE 0.0
    END AS projected_amount_2021
  FROM pivoted_sales
), projected_sales_usd AS (
  SELECT
    ps.calendar_month_number,
    ps.prod_id,
    ps.projected_amount_2021 * cur.to_us AS projected_amount_usd
  FROM projected_sales_2021 AS ps
  JOIN main.currency AS cur
    ON cur.country = 'France' AND cur.year = 2021 AND cur.month = ps.calendar_month_number
), monthly_total_projected_sales_usd AS (
  SELECT
    calendar_month_number,
    SUM(projected_amount_usd) AS total_monthly_projected_sales_usd
  FROM projected_sales_usd
  GROUP BY
    calendar_month_number
), ranked_monthly_sales AS (
  SELECT
    total_monthly_projected_sales_usd,
    ROW_NUMBER() OVER (ORDER BY total_monthly_projected_sales_usd) AS rn,
    COUNT(*) OVER () AS total_months
  FROM monthly_total_projected_sales_usd
)
SELECT
  AVG(total_monthly_projected_sales_usd)
FROM ranked_monthly_sales
WHERE
  rn = (total_months / 2) OR rn = (total_months / 2) + 1