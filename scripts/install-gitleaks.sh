#!/usr/bin/env bash
# Install gitleaks v8.30.1, the same revision as .pre-commit-config.yaml.
# Planted-violation tests call the binary on PATH. They do not run this script.
set -euo pipefail

version="8.30.1"
archive="gitleaks_${version}_linux_x64.tar.gz"
checksum="551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"
prefix="${PREFIX:-${HOME}/.local}"
destination="${prefix}/bin/gitleaks"
url="https://github.com/gitleaks/gitleaks/releases/download/v${version}/${archive}"

if [[ -x "${destination}" ]]; then
  installed="$("${destination}" version 2>/dev/null || true)"
  if [[ "${installed}" == "${version}" ]]; then
    if [[ -n "${GITHUB_PATH:-}" ]]; then
      echo "${prefix}/bin" >> "${GITHUB_PATH}"
    fi
    exit 0
  fi
fi

workdir="$(mktemp -d)"
trap 'rm -rf "${workdir}"' EXIT
curl --fail --silent --show-error --location --output "${workdir}/${archive}" "${url}"
echo "${checksum}  ${workdir}/${archive}" | sha256sum --check -
tar --extract --gzip --file "${workdir}/${archive}" --directory "${workdir}" gitleaks
mkdir -p "${prefix}/bin"
install -m 0755 "${workdir}/gitleaks" "${destination}"
if [[ -n "${GITHUB_PATH:-}" ]]; then
  echo "${prefix}/bin" >> "${GITHUB_PATH}"
fi
