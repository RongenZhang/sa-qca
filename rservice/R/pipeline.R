# SA-QCA computation core.
#
# PURE: no global state, no randomness, no discretion. Every value that affects the result
# (anchors, cutoffs, directional expectations) arrives as an argument and is used as given.
# Nothing here trims, clamps, rounds or repairs input.

suppressPackageStartupMessages({
  library(QCA)
  library(jsonlite)
})

ANCHOR_KEYS <- c("full_non_membership", "crossover", "full_membership")

check_input <- function(input) {
  stopifnot(is.list(input), !is.null(input$data), !is.null(input$conditions), !is.null(input$outcome),
            !is.null(input$truth_table))
  vars <- c(vapply(input$conditions, function(v) v$name, ""), input$outcome$name)
  missing_cols <- setdiff(vars, names(input$data))
  if (length(missing_cols) > 0) stop("data is missing columns: ", paste(missing_cols, collapse = ", "))
  for (v in c(input$conditions, list(input$outcome))) {
    if (!all(ANCHOR_KEYS %in% names(v$anchors))) stop("anchors incomplete for ", v$name)
  }
  invisible(TRUE)
}

# Direct-method calibration. QCA::calibrate infers direction from the order of e, c, i
# (e < c < i increasing; e > c > i decreasing), so orientation is carried by the anchors.
calibrate_variable <- function(x, anchors) {
  th <- c(e = anchors$full_non_membership, c = anchors$crossover, i = anchors$full_membership)
  as.numeric(unclass(QCA::calibrate(x, type = "fuzzy", thresholds = th, logistic = TRUE, idm = 0.95)))
}

# Canonical representation of a solution term: sorted signed literals, e.g. "+A", "-B".
term_literals <- function(term) {
  lits <- strsplit(term, "\\*", perl = TRUE)[[1]]
  # radix sort is locale-independent, which keeps output byte-identical across machines
  sort(ifelse(startsWith(lits, "~"), paste0("-", sub("^~", "", lits)), paste0("+", lits)), method = "radix")
}

extract_solution <- function(models, ic_list) {
  # models: list of character vectors (terms per model); ic_list: list of IC objects per model
  out <- lapply(seq_along(models), function(k) {
    terms <- models[[k]]
    ic <- ic_list[[k]]
    inc <- ic$incl.cov
    sol <- ic$sol.incl.cov
    ord <- order(terms, method = "radix")
    list(
      terms = lapply(terms[ord], function(t) list(
        expression = t,
        literals = as.list(term_literals(t)),
        inclS = if (!is.null(inc) && t %in% rownames(inc)) inc[t, "inclS"] else NA_real_,
        PRI   = if (!is.null(inc) && t %in% rownames(inc)) inc[t, "PRI"] else NA_real_,
        covS  = if (!is.null(inc) && t %in% rownames(inc)) inc[t, "covS"] else NA_real_
      )),
      solution_fit = if (!is.null(sol)) list(inclS = sol[1, "inclS"], PRI = sol[1, "PRI"], covS = sol[1, "covS"]) else NULL
    )
  })
  keys <- vapply(out, function(m) paste(vapply(m$terms, function(t) t$expression, ""), collapse = " + "), "")
  out[order(keys, method = "radix")]
}

solution_block <- function(res) {
  models <- res$solution
  ics <- if (!is.null(res$IC) && !is.null(res$IC$incl.cov)) rep(list(res$IC), length(models)) else vector("list", length(models))
  if (length(models) == 0 || all(lengths(models) == 0)) return(list(models = list(), n_models = 0L))
  # QCA returns one IC when models are non-unique in $IC, and per-model ICs in $IC$individual
  if (!is.null(res$IC$individual)) ics <- res$IC$individual
  list(models = extract_solution(models, ics), n_models = length(models))
}

run_pipeline <- function(input) {
  started_versions <- list(
    R = R.version.string,
    QCA = as.character(utils::packageVersion("QCA")),
    jsonlite = as.character(utils::packageVersion("jsonlite"))
  )
  result <- list(status = "ok", versions = started_versions)
  tryCatch({
    check_input(input)
    cond_names <- vapply(input$conditions, function(v) v$name, "")
    out_name <- input$outcome$name

    cal <- data.frame(lapply(setNames(cond_names, cond_names),
      function(n) calibrate_variable(as.numeric(input$data[[n]]),
        input$conditions[[match(n, cond_names)]]$anchors)), check.names = FALSE)
    cal[[out_name]] <- calibrate_variable(as.numeric(input$data[[out_name]]), input$outcome$anchors)
    result$calibrated <- as.list(cal)

    tt_args <- input$truth_table
    tt <- suppressWarnings(QCA::truthTable(
      cal, outcome = out_name, conditions = paste(cond_names, collapse = ","),
      incl.cut = tt_args$consistency_threshold, n.cut = tt_args$frequency_threshold,
      pri.cut = if (is.null(tt_args$pri_threshold)) 0 else tt_args$pri_threshold,
      show.cases = FALSE))
    ttdf <- tt$tt
    result$truth_table <- list(
      rows = lapply(seq_len(nrow(ttdf)), function(i) c(
        as.list(ttdf[i, cond_names, drop = FALSE]),
        list(OUT = as.character(ttdf$OUT[i]), n = ttdf$n[i], incl = ttdf$incl[i], PRI = ttdf$PRI[i]))),
      cutoffs_used = list(consistency = tt_args$consistency_threshold, frequency = tt_args$frequency_threshold,
                          pri = if (is.null(tt_args$pri_threshold)) 0 else tt_args$pri_threshold)
    )

    result$necessity <- lapply(cond_names, function(n) {
      f <- function(expr) {
        x <- QCA::pof(expr, out_name, cal, relation = "necessity")$incl.cov
        list(expression = expr, inclN = x[1, "inclN"], RoN = x[1, "RoN"], covN = x[1, "covN"])
      }
      list(condition = n, present = f(n), negated = f(paste0("~", n)))
    })

    # Positive-outcome truth table rows must exist for minimization.
    has_pos <- any(as.character(ttdf$OUT) == "1")
    if (!has_pos) {
      result$status <- "valid_no_solution"
      result$solutions <- list(complex = list(models = list(), n_models = 0L),
                               parsimonious = list(models = list(), n_models = 0L),
                               intermediate = NULL)
    } else {
      cx <- suppressWarnings(QCA::minimize(tt, include = "", details = TRUE))
      pa <- suppressWarnings(QCA::minimize(tt, include = "?", details = TRUE))
      sols <- list(complex = solution_block(cx), parsimonious = solution_block(pa), intermediate = NULL)
      de <- vapply(input$conditions, function(v) if (is.null(v$dir_exp)) "-" else as.character(v$dir_exp), "")
      if (any(de != "-")) {
        im <- suppressWarnings(QCA::minimize(tt, include = "?", dir.exp = paste(de, collapse = ","), details = TRUE))
        models <- lapply(im$i.sol, function(m) m$solution[[1]])
        ics <- lapply(im$i.sol, function(m) m$IC)
        sols$intermediate <- list(models = extract_solution(models, ics), n_models = length(models))
      }
      result$solutions <- sols
      if (length(sols$complex$models) == 0) result$status <- "valid_no_solution"
    }
  }, error = function(e) {
    msg <- conditionMessage(e)
    if (grepl("no configurations", msg, fixed = TRUE)) {
      # The supplied cutoffs leave no truth-table rows: a legitimate empty result, not a failure.
      result$status <<- "valid_no_solution"
      result$note <<- trimws(msg)
    } else {
      result$status <<- "r_error"
      result$error <<- msg
    }
  })
  result
}

# Canonical JSON: fixed key order is preserved from construction, full double precision, no pretty-printing.
canonical_json <- function(x) {
  as.character(jsonlite::toJSON(x, auto_unbox = TRUE, digits = NA, null = "null", na = "null", pretty = FALSE))
}

run_pipeline_json <- function(json_string) {
  input <- jsonlite::fromJSON(json_string, simplifyVector = TRUE, simplifyDataFrame = FALSE, simplifyMatrix = FALSE)
  canonical_json(run_pipeline(input))
}
