# Generates demo/dataset.csv (synthetic; not real data). Seeded so the file is reproducible.
set.seed(20260929)
n <- 60
trust     <- round(pmin(7, pmax(1, rnorm(n, 4.4, 1.3))), 2)   # 1-7 Likert composite
support   <- round(pmin(7, pmax(1, rnorm(n, 4.0, 1.5))), 2)   # 1-7
resources <- round(pmin(100, pmax(0, rnorm(n, 50, 22))), 1)   # 0-100 index
lat <- 0.35*scale(trust) + 0.30*scale(support) + 0.25*scale(resources) + 0.5*scale(trust*support) + rnorm(n, 0, 0.6)
adoption  <- round(pmin(100, pmax(0, 50 + 18*lat)), 1)        # 0-100 index
write.csv(data.frame(case = sprintf("C%02d", 1:n), TRUST = trust, SUPPORT = support,
                     RESOURCES = resources, ADOPTION = adoption), "demo/dataset.csv", row.names = FALSE)
