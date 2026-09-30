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
