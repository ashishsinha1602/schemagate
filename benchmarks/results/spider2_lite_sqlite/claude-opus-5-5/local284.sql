WITH stats AS (
  SELECT AVG("loss_rate_%") AS avg_loss,
         COUNT(*) AS n
  FROM veg_loss_rate_df
),
var AS (
  SELECT s.avg_loss,
         SUM((l."loss_rate_%" - s.avg_loss) * (l."loss_rate_%" - s.avg_loss)) / (s.n - 1) AS variance
  FROM veg_loss_rate_df l CROSS JOIN stats s
)
SELECT v.avg_loss AS average_loss_rate,
       SUM(CASE WHEN l."loss_rate_%" < v.avg_loss
                 AND (l."loss_rate_%" - v.avg_loss) * (l."loss_rate_%" - v.avg_loss) > v.variance
                THEN 1 ELSE 0 END) AS below_one_sd_count,
       SUM(CASE WHEN (l."loss_rate_%" - v.avg_loss) * (l."loss_rate_%" - v.avg_loss) <= v.variance
                THEN 1 ELSE 0 END) AS within_one_sd_count,
       SUM(CASE WHEN l."loss_rate_%" > v.avg_loss
                 AND (l."loss_rate_%" - v.avg_loss) * (l."loss_rate_%" - v.avg_loss) > v.variance
                THEN 1 ELSE 0 END) AS above_one_sd_count
FROM veg_loss_rate_df l CROSS JOIN var v