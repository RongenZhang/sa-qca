# Stateless HTTP wrapper. Run: Rscript -e 'plumber::pr("plumber.R") |> plumber::pr_run(host="0.0.0.0", port=8000)'
source("R/pipeline.R")

#* @get /health
function() list(status = "ok", QCA = as.character(utils::packageVersion("QCA")))

#* @post /run_pipeline
#* @serializer contentType list(type="application/json")
function(req) run_pipeline_json(req$postBody)
