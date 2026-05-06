#!/usr/bin/env bash
set -euo pipefail
model=${1:?model name required}
buf=${2:-512}
topology="topologies/ispass25_models/${model}.csv"
python3 -m scalesim.scale -c ./configs/google.cfg -t "${topology}" --save-trace > "${model}_${buf}_orig_out"
python3 scripts/dram_sim.py -topology "${model}" -run_name GoogleTPU_v1_os -jobs "${JOBS:-1}"
python3 scripts/dram_latency.py -topology "${model}" -parallel true -jobs "${JOBS:-1}"
python3 -m scalesim.scale -c ./configs/google_ramulator.cfg -t "${topology}" --no-save-trace > "${model}_${buf}_stall_out"
mkdir -p ./results/dram_results/stall_cycles
cp "${model}_${buf}_orig_out" ./results/dram_results/stall_cycles/
cp "${model}_${buf}_stall_out" ./results/dram_results/stall_cycles/
