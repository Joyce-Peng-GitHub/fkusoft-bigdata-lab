#!/usr/bin/env bash
# Download the UrbanEV zone-level hourly CSVs (CC0) from the official GitHub repo.
# ~110MB total. Output goes to urbanev/data/raw/ which is git-ignored.
#
# Usage:
#   urbanev/fetch_data.sh                       # default dir + lab proxy
#   URBANEV_DIR=/some/dir urbanev/fetch_data.sh # custom output dir
#   URBANEV_PROXY= urbanev/fetch_data.sh        # direct access (no proxy)
set -euo pipefail

DIR="${URBANEV_DIR:-$(cd "$(dirname "$0")" && pwd)/data/raw}"
# The lab network blocks direct GitHub raw access; default to the lab proxy.
PROXY="${URBANEV_PROXY-${https_proxy-http://10.194.0.60:7897}}"
BASE="https://raw.githubusercontent.com/IntelligentSystemsLab/UrbanEV/main/data"

# Core hourly wide tables (time + 275 zone columns) plus features and dimensions.
FILES=(
  volume.csv volume-11kW.csv occupancy.csv duration.csv
  e_price.csv s_price.csv
  weather_central.csv weather_airport.csv weather_header.txt
  inf.csv inf_raw.csv adj.csv distance.csv poi.csv
)

mkdir -p "$DIR"
CURL_ARGS=( -fsSL --retry 3 --connect-timeout 15 )
[ -n "$PROXY" ] && CURL_ARGS+=( -x "$PROXY" )

for f in "${FILES[@]}"; do
  if [ -s "$DIR/$f" ]; then
    echo "skip existing $DIR/$f"
    continue
  fi
  echo "downloading $f ..."
  curl "${CURL_ARGS[@]}" -o "$DIR/$f" "$BASE/$f"
done

echo "done. files in: $DIR"
ls -la "$DIR"
