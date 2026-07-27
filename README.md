# VersusWorld

VersusBot world tournament bot.

## Setup

```bash
uv sync
cp .env.example .env
```

Fill in `MONGO_DB_URI`, `MONGO_DB_NAME`, and `PAGE_ACCESS_TOKEN`.


## Run

```bash
# seed DB
uv run versusworld init

# one cycle (resolve last match + post next)
uv run versusworld run

# every 4 hours
uv run versusworld schedule

# local preview (no Mongo / no FB)
uv run versusworld init --local
uv run versusworld preview --c1 US --c2 CA
```

Other commands: `status`, `run --local`, `init --force`.
