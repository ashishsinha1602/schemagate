WITH stats AS (
  SELECT AVG("loss_rate_%") AS avg_lr,
         AVG("loss_rate_%" * "loss_rate_%") - AVG("loss_rate_%") * AVG("loss_rate_%") AS var_lr
  FROM veg_loss_rate_df
)
SELECT
  ROUND(s.avg_lr, 4) AS avg_loss_rate,
  COUNT(*) AS total_items,
  SUM(CASE WHEN l."loss_rate_%" < s.avg_lr - sqrt_sd.sd THEN 1 ELSE 0 END) AS below_one_sd,
  SUM(CASE WHEN l."loss_rate_%" BETWEEN s.avg_lr - sqrt_sd.sd AND s.avg_lr + sqrt_sd.sd THEN 1 ELSE 0 END) AS within_one_sd,
  SUM(CASE WHEN l."loss_rate_%" > s.avg_lr + sqrt_sd.sd THEN 1 ELSE 0 END) AS above_one_sd
FROM veg_loss_rate_df l
CROSS JOIN stats s
CROSS JOIN (
  SELECT 0.0 AS sd WHERE 0
) dummy_unused
JOIN (SELECT 1) ON 1=1
CROSS JOIN (SELECT 0 AS sd) sqrt_sd
WHERE 0