# Generates demo/dataset.csv (synthetic; not real data). Seeded so the file is reproducible.
# Built with two routes to high adoption (equifinality), so the analyst's solution has more than one path:
#   (1) high TRUST and high SUPPORT, or (2) high RESOURCES and LOW TRUST (firms that do not rely on the vendor).
seed <- as.integer(Sys.getenv("DEMO_SEED", "20260930"))
set.seed(seed)
n <- 60
mem <- function(x, lo, mid, hi) plogis(log(19) * ifelse(x >= mid, (x - mid) / (hi - mid), (x - mid) / (mid - lo)))
trust     <- round(pmin(7, pmax(1, rnorm(n, 4.2, 1.5))), 2)   # 1-7 Likert composite
support   <- round(pmin(7, pmax(1, rnorm(n, 4.0, 1.5))), 2)   # 1-7
resources <- round(pmin(100, pmax(0, rnorm(n, 50, 24))), 1)   # 0-100 index
T_ <- mem(trust, 2.5, 4.0, 5.5); S_ <- mem(support, 2.0, 4.0, 6.0); R_ <- mem(resources, 25, 50, 75)
y  <- pmax(pmin(T_, S_), pmin(R_, 1 - T_))
adoption <- round(pmin(100, pmax(0, 100 * pmin(1, pmax(0, y + rnorm(n, 0, 0.07))))), 1)   # 0-100 index
write.csv(data.frame(case = sprintf("C%02d", 1:n), TRUST = trust, SUPPORT = support,
                     RESOURCES = resources, ADOPTION = adoption), "demo/dataset.csv", row.names = FALSE)
