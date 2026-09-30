# SA-QCA replication script. Re-runs the QCA computation for every stored judgment with NO LLM calls,
# and checks that each result is identical to the one recorded at run time.
#
# Usage (from the bundle root):   Rscript replication/replicate.R
# Requires R with packages: QCA, jsonlite.  Exit status 0 = every run reproduced, 1 = at least one differs.

args <- commandArgs(trailingOnly = TRUE)
root <- normalizePath(if (length(args) >= 1) args[1] else ".")
suppressPackageStartupMessages(library(jsonlite))
source(file.path(root, "replication", "pipeline.R"))   # same computation code as the original runs

spec <- fromJSON(file.path(root, "replication", "spec.json"), simplifyVector = FALSE)
flags <- list(simplifyVector = TRUE, simplifyDataFrame = FALSE, simplifyMatrix = FALSE)  # as at run time
data <- do.call(fromJSON, c(list(file.path(root, "data", "analysis_data.json")), flags))

rows <- list()
for (r in spec$runs) {
  input <- do.call(fromJSON, c(list(file.path(root, r$input_file)), flags))
  input$data <- data
  got <- fromJSON(canonical_json(run_pipeline(input)), simplifyVector = FALSE)
  exp <- fromJSON(file.path(root, r$expected_file), simplifyVector = FALSE)
  kg <- setdiff(names(got), "versions"); ke <- setdiff(names(exp), "versions")
  same <- identical(kg, ke) && identical(got[kg], exp[ke])
  rows[[length(rows) + 1]] <- list(run_id = r$run_id, arm = r$arm, match = same)
  cat(sprintf("run %s (%s): %s\n", r$run_id, r$arm, if (same) "MATCH" else "MISMATCH"))
}

ok <- vapply(rows, function(x) isTRUE(x$match), logical(1))
check <- list(
  n_runs = length(rows), n_match = sum(ok), n_mismatch = sum(!ok),
  mismatched_run_ids = vapply(rows[!ok], function(x) as.integer(x$run_id), integer(1)),
  replication_environment = list(R = R.version.string, QCA = as.character(packageVersion("QCA")),
                                 jsonlite = as.character(packageVersion("jsonlite"))),
  original_environment = spec$original_environment
)
dir.create(file.path(root, "results"), showWarnings = FALSE)
write(toJSON(check, auto_unbox = TRUE, pretty = TRUE, digits = NA), file.path(root, "results", "replication_check.json"))
capture.output(sessionInfo(), file = file.path(root, "replication", "sessionInfo_replication.txt"))
cat(sprintf("\n%d of %d runs reproduced exactly.\n", sum(ok), length(ok)))
quit(status = if (all(ok)) 0 else 1)
