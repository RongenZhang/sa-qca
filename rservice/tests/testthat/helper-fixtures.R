root <- normalizePath(file.path("..", "..", ".."), mustWork = FALSE)
demo_input <- function() {
  d <- read.csv(file.path(root, "demo", "dataset.csv"))
  p <- jsonlite::fromJSON(file.path(root, "demo", "project.json"), simplifyVector = FALSE)
  rs <- p$reference_spec
  list(data = as.list(d[, -1]),
       conditions = lapply(p$variables[1:3], function(v)
         list(name = v$name, direction = v$direction, dir_exp = v$dir_exp, anchors = rs[[v$name]])),
       outcome = list(name = "ADOPTION", direction = "positive", anchors = rs$ADOPTION),
       truth_table = rs$truth_table)
}
