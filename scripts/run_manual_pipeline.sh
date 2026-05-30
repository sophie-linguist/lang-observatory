#!/bin/bash
cd /home/ssohe/lang-observatory
source venv/bin/activate
export PYTHONPATH=src

./scripts/run_pipeline.sh morphemes
./scripts/run_pipeline.sh refresh
./scripts/run_pipeline.sh embed
./scripts/run_pipeline.sh segment_map
./scripts/run_pipeline.sh eojeol
