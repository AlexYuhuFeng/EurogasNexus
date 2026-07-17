#!/usr/bin/env bash
set -euo pipefail

readonly MAX_ATTEMPTS=4
readonly -a PACKAGES=(
  build-essential
  curl
  file
  libayatana-appindicator3-dev
  librsvg2-dev
  libssl-dev
  libwebkit2gtk-4.1-dev
  patchelf
  wget
)

# ARM runners have intermittently failed on the plain-HTTP Ubuntu ports mirror.
# Keep the official mirror while preferring its HTTPS endpoint.
for source_file in /etc/apt/sources.list /etc/apt/sources.list.d/ubuntu.sources; do
  if [[ -f "${source_file}" ]]; then
    sudo sed -i \
      -e 's|http://ports.ubuntu.com|https://ports.ubuntu.com|g' \
      -e 's|http://archive.ubuntu.com|https://archive.ubuntu.com|g' \
      "${source_file}"
  fi
done

for attempt in $(seq 1 "${MAX_ATTEMPTS}"); do
  echo "Installing Linux Tauri dependencies (attempt ${attempt}/${MAX_ATTEMPTS})"
  if sudo apt-get -o Acquire::Retries=3 update && \
    sudo DEBIAN_FRONTEND=noninteractive apt-get \
      -o Acquire::Retries=3 \
      install -y --no-install-recommends "${PACKAGES[@]}"; then
    exit 0
  fi

  if [[ "${attempt}" -lt "${MAX_ATTEMPTS}" ]]; then
    sudo apt-get clean
    sleep $((attempt * 15))
  fi
done

echo "Linux Tauri dependency installation failed after ${MAX_ATTEMPTS} attempts." >&2
exit 1
