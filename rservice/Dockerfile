FROM rocker/r-ver:4.5.1
RUN apt-get update && apt-get install -y --no-install-recommends libcurl4-openssl-dev libssl-dev libxml2-dev libsodium-dev && rm -rf /var/lib/apt/lists/*
RUN R -e 'options(repos="https://packagemanager.posit.co/cran/2025-09-01"); install.packages(c("QCA","SetMethods","plumber","jsonlite","testthat"))'
WORKDIR /app
COPY R ./R
COPY plumber.R .
EXPOSE 8000
CMD ["Rscript", "-e", "plumber::pr('plumber.R') |> plumber::pr_run(host='0.0.0.0', port=8000)"]
