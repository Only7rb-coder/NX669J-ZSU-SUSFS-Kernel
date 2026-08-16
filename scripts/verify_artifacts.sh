#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/config/device.env"

[[ -s "$ROOT_DIR/artifacts/Image" ]]
grep -q '^KSU_NEXT_MANAGER_LIST := 0x318:ba1159a5819dec96cdcb2498bef73170b0ba1735c12139bde1b7677bf7c5c2ab$' "$ROOT_DIR/kernel/KernelSU-Next/kernel/Kbuild"
unzip -t "$ROOT_DIR/artifacts/NX669J-ZSU-SUSFS-AnyKernel3.zip" >/dev/null
unzip -p "$ROOT_DIR/artifacts/NX669J-ZSU-SUSFS-AnyKernel3.zip" anykernel.sh | grep -q 'split_boot'
unzip -p "$ROOT_DIR/artifacts/NX669J-ZSU-SUSFS-AnyKernel3.zip" anykernel.sh | grep -q 'flash_boot'
! unzip -p "$ROOT_DIR/artifacts/NX669J-ZSU-SUSFS-AnyKernel3.zip" anykernel.sh | grep -qE '^[[:space:]]*(dump_boot|write_boot)'

echo 'NX669J artifact validation passed.'
printf 'Image bytes: '
stat -c '%s' "$ROOT_DIR/artifacts/Image"
printf 'AnyKernel bytes: '
stat -c '%s' "$ROOT_DIR/artifacts/NX669J-ZSU-SUSFS-AnyKernel3.zip"
