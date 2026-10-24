WITH cleaned AS (
  SELECT
    report_number,
    SPLIT(reactions, ',') AS reactions,
    SPLIT(outcomes, ',') AS outcomes,
    REPLACE(REPLACE(REGEXP_REPLACE(products_brand_name, r'(\d), (\d)', r'\1<<NUMCOMMA>>\2'), ', ', ' -- '), '<<NUMCOMMA>>', ', ') AS products_brand_name,
    REPLACE(products_industry_code, ', ', ' -- ') AS products_industry_code,
    REPLACE(products_role, ', ', ' -- ') AS products_role,
    REPLACE(products_industry_name, ', ', ' -- ') AS products_industry_name,
    date_created,
    date_started,
    consumer_gender,
    consumer_age,
    consumer_age_unit
  FROM `bigquery-public-data.fda_food.food_events`
  WHERE date_created BETWEEN DATE '2015-01-01' AND DATE '2015-01-31'
    AND date_started BETWEEN DATE '2015-01-01' AND DATE '2015-01-31'
)
SELECT
  report_number,
  reactions,
  outcomes,
  products_brand_name,
  products_industry_code,
  products_role,
  products_industry_name,
  date_created,
  date_started,
  consumer_gender,
  consumer_age,
  consumer_age_unit,
  ARRAY_LENGTH(SPLIT(products_industry_code, ' -- ')) AS industry_code_length,
  ARRAY_LENGTH(SPLIT(products_brand_name, ' -- ')) AS brand_name_length
FROM cleaned