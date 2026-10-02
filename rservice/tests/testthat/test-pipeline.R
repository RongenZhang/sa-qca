source("../../R/pipeline.R")

test_that("determinism: identical inputs give byte-identical canonical output", {
  inp <- demo_input()
  a <- canonical_json(run_pipeline(inp))
  b <- canonical_json(run_pipeline(inp))
  expect_identical(a, b)
  # and through the JSON entry point used by the HTTP service
  js <- jsonlite::toJSON(inp, auto_unbox = TRUE, digits = NA)
  expect_identical(run_pipeline_json(js), run_pipeline_json(js))
})

test_that("determinism holds across data row order changes only in ways QCA defines (same order => same)", {
  inp <- demo_input()
  expect_identical(canonical_json(run_pipeline(inp)), canonical_json(run_pipeline(inp)))
})

test_that("input is not mutated by the pipeline", {
  inp <- demo_input(); before <- inp
  invisible(run_pipeline(inp))
  expect_identical(inp, before)
})

test_that("calibration: anchors map to 0.05 / 0.5 / 0.95 (increasing)", {
  a <- list(full_non_membership = 2, crossover = 4, full_membership = 6)
  v <- calibrate_variable(c(2, 4, 6), a)
  expect_equal(v, c(0.05, 0.5, 0.95), tolerance = 1e-9)
})

test_that("calibration: reversed anchors give a decreasing set (negative orientation)", {
  a <- list(full_non_membership = 6, crossover = 4, full_membership = 2)
  v <- calibrate_variable(c(2, 4, 6), a)
  expect_equal(v, c(0.95, 0.5, 0.05), tolerance = 1e-9)
})

test_that("pipeline calibrated output equals direct QCA::calibrate", {
  inp <- demo_input(); r <- run_pipeline(inp)
  direct <- as.numeric(unclass(QCA::calibrate(inp$data$TRUST, type = "fuzzy",
              thresholds = c(e = 2.5, c = 4.0, i = 5.5))))
  expect_identical(r$calibrated$TRUST, direct)
})

test_that("known answer: Ragin's Lipset data, parsimonious solution DEV*~IND + URB*STB (incl.cut 0.8)", {
  data(LF, package = "QCA")
  tt <- suppressWarnings(QCA::truthTable(LF, outcome = "SURV", conditions = "DEV,URB,LIT,IND,STB",
                                         incl.cut = 0.8, n.cut = 1, pri.cut = 0, show.cases = FALSE))
  m <- suppressWarnings(QCA::minimize(tt, include = "?", details = TRUE))
  expect_setequal(m$solution[[1]], c("DEV*~IND", "URB*STB"))
})

test_that("term literals canonicalise negation and order", {
  expect_identical(term_literals("B*~A"), term_literals("~A*B"))
  expect_identical(term_literals("A*~B"), c("+A", "-B"))
})

test_that("solution block shape and status", {
  r <- run_pipeline(demo_input())
  expect_true(r$status %in% c("ok", "valid_no_solution"))
  expect_named(r$solutions, c("complex", "parsimonious", "intermediate"))
  expect_equal(length(r$necessity), 3)
})

test_that("missing anchors -> r_error, not a silent repair", {
  inp <- demo_input(); inp$conditions[[1]]$anchors$crossover <- NULL
  r <- run_pipeline(inp)
  expect_identical(r$status, "r_error")
  expect_match(r$error, "anchors incomplete")
})

test_that("missing column -> r_error", {
  inp <- demo_input(); inp$data$TRUST <- NULL
  expect_identical(run_pipeline(inp)$status, "r_error")
})

test_that("no positive truth-table rows -> valid_no_solution", {
  inp <- demo_input(); inp$truth_table$consistency_threshold <- 1.0; inp$truth_table$frequency_threshold <- 500
  expect_identical(run_pipeline(inp)$status, "valid_no_solution")
})

test_that("intermediate solution only when directional expectations supplied", {
  inp <- demo_input()
  for (i in seq_along(inp$conditions)) inp$conditions[[i]]$dir_exp <- NULL
  expect_null(run_pipeline(inp)$solutions$intermediate)
})

test_that("demo dataset recovers its two built-in routes (equifinality) under the analyst's specification", {
  r <- run_pipeline(demo_input())
  for (kind in c("complex", "parsimonious", "intermediate")) {
    terms <- vapply(r$solutions[[kind]]$models[[1]]$terms, function(t) t$expression, "")
    expect_setequal(terms, c("TRUST*SUPPORT", "~TRUST*RESOURCES"))
  }
})


# ---- calibration kinds -------------------------------------------------------------------------------------

isj_input <- function(breaks = list(break_0 = 0, break_33 = 15, break_67 = 90)) {
  d <- read.csv(file.path(root, "rservice", "tests", "testthat", "fixtures", "zhang_ramesh_2024_isj.csv"), stringsAsFactors = FALSE)
  conds <- c("ACC", "VISI", "AUTO", "INCEN1", "INCEN2")
  list(data = c(as.list(d[, conds]), list(Posts = d$Posts)),
       conditions = lapply(conds, function(n) list(name = n, direction = "positive", dir_exp = NULL,
                                                   calibration = list(kind = "precalibrated"))),
       outcome = list(name = "Posts", direction = "positive", calibration = list(kind = "breakpoints", breakpoints = breaks)),
       truth_table = list(consistency_threshold = 0.8, frequency_threshold = 1, pri_threshold = 0.75))
}

test_that("breakpoints: positive orientation, boundary values take the lower score", {
  b <- list(break_0 = 0, break_33 = 15, break_67 = 90)
  expect_equal(calibrate_breakpoints(c(0, 1, 15, 16, 90, 91), b), c(0, 0.33, 0.33, 0.67, 0.67, 1))
})

test_that("breakpoints: negative orientation mirrors the comparisons", {
  b <- list(break_0 = 100, break_33 = 50, break_67 = 10)
  expect_equal(calibrate_breakpoints(c(120, 100, 99, 50, 49, 10, 9), b), c(0, 0, 0.33, 0.33, 0.67, 0.67, 1))
})

test_that("breakpoints must be finite and strictly ordered", {
  expect_error(calibrate_breakpoints(1:3, list(break_0 = 0, break_33 = 5, break_67 = 5)), "strictly")
  expect_error(calibrate_breakpoints(1:3, list(break_0 = 0, break_33 = 9, break_67 = 5)), "strictly")
  expect_error(calibrate_breakpoints(1:3, list(break_0 = NA, break_33 = 5, break_67 = 9)), "finite")
})

test_that("pass-through keeps memberships exactly and refuses anything outside [0, 1]", {
  x <- c(0, 0.33, 0.67, 1, 0.123456789012345)
  expect_identical(passthrough_variable(x, "A"), x)
  expect_error(passthrough_variable(c(0.5, 1.2), "A"), "memberships in \\[0, 1\\]")
  expect_error(passthrough_variable(c(0.5, NA), "A"), "memberships in \\[0, 1\\]")
})

test_that("inputs without a calibration field behave exactly as direct calibration (older runs still replicate)", {
  old <- demo_input()
  new <- old
  new$conditions <- lapply(old$conditions, function(v) { v$calibration <- list(kind = "direct", anchors = v$anchors); v$anchors <- NULL; v })
  new$outcome$calibration <- list(kind = "direct", anchors = old$outcome$anchors); new$outcome$anchors <- NULL
  expect_identical(canonical_json(run_pipeline(old)), canonical_json(run_pipeline(new)))
})

test_that("unknown calibration kinds and incomplete breakpoints are errors, not guesses", {
  bad <- isj_input(); bad$outcome$calibration$kind <- "magic"
  expect_match(run_pipeline(bad)$error, "unknown calibration kind")
  bad <- isj_input(list(break_0 = 0, break_33 = 15)); expect_match(run_pipeline(bad)$error, "breakpoints incomplete")
})

test_that("KNOWN ANSWER (Zhang & Ramesh 2024, ISJ): breakpoints 0/15/90 reproduce the published outcome and solution", {
  r <- run_pipeline(isj_input())
  expect_identical(r$status, "ok")
  published_gen_eng <- c(0.67, 0.67, 1, 0.67, 1, 0.67, 0.33, 0.67, 0.67, 1, 0.33, 0.67, 0.33, 0.33)
  expect_equal(r$calibrated$Posts, published_gen_eng)
  terms <- vapply(r$solutions$complex$models[[1]]$terms, function(t) t$expression, "")
  expect_setequal(terms, c("ACC*VISI*AUTO*~INCEN2", "ACC*AUTO*INCEN1*INCEN2", "VISI*AUTO*INCEN1*~INCEN2"))
  fit <- r$solutions$complex$models[[1]]$solution_fit
  expect_equal(fit$inclS, 1.000, tolerance = 5e-4)   # Table 4: overall solution consistency 1.000
  expect_equal(fit$PRI, 1.000, tolerance = 5e-4)     # overall solution PRI 1.000
  expect_equal(fit$covS, 0.815, tolerance = 5e-4)    # overall solution coverage 0.815
})

test_that("different breakpoints change the calibrated outcome and are reported, not hidden", {
  a <- run_pipeline(isj_input())
  b <- run_pipeline(isj_input(list(break_0 = 0, break_33 = 10, break_67 = 60)))
  expect_false(identical(a$calibrated$Posts, b$calibrated$Posts))
  expect_identical(b$status %in% c("ok", "valid_no_solution"), TRUE)
})
