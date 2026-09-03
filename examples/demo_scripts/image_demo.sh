#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${script_dir}/../app.py" ]]; then
  project_root="$(cd -- "${script_dir}/.." && pwd)"
else
  project_root="$(cd -- "${script_dir}/../.." && pwd)"
fi
python_bin="${project_root}/.venv/bin/python"
if [[ ! -x "${python_bin}" ]]; then python_bin="python"; fi

"${python_bin}" -m streamlit run "${project_root}/app.py" \
  --server.address 0.0.0.0 \
  --server.port 10081 \
  --server.fileWatcherType none \
  -- \
  --mode image \
  --title "图片实验结果展示与标注" \
  --data-dir "${project_root}/sample_data/image"
