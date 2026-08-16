#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KERNEL_DIR="${KERNEL_DIR:-$ROOT_DIR/kernel}"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/out}"
CONFIG_FILE="$ROOT_DIR/config/device.env"

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Missing $CONFIG_FILE" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$CONFIG_FILE"

export ARCH="${KERNEL_ARCH:-arm64}"
export CROSS_COMPILE="${CROSS_COMPILE:-aarch64-linux-gnu-}"
export CLANG_TRIPLE="${CLANG_TRIPLE:-aarch64-linux-gnu-}"
export REAL_CC="${REAL_CC:-clang}"
export HOSTCC="${HOSTCC:-gcc}"
export HOSTLD="${HOSTLD:-ld}"
export HOSTAR="${HOSTAR:-ar}"
export TARGET_NUBIA_SSD="${TARGET_NUBIA_SSD:-false}"
export NUBIA_TARGET_PRODUCT="${NUBIA_TARGET_PRODUCT:-NX669J}"
export TARGET_BUILD_VARIANT="${TARGET_BUILD_VARIANT:-user}"
export PRODUCT_BUILD_NX669J_S="${PRODUCT_BUILD_NX669J_S:-false}"
export PRODUCT_BUILD_NX669J_N="${PRODUCT_BUILD_NX669J_N:-false}"

mkdir -p "$ROOT_DIR/deps" "$OUT_DIR"

if [[ ! -d "$KERNEL_DIR/arch/arm64" ]]; then
  git clone --depth 1 --branch "$KERNEL_REF" "$KERNEL_REPO" "$KERNEL_DIR"
fi

cd "$KERNEL_DIR"

# KernelSU-Next's maintained setup script integrates drivers/kernelsu into both
# common-style GKI trees and ordinary Qualcomm kernel trees.
if [[ ! -d KernelSU-Next ]]; then
  curl -fsSL https://raw.githubusercontent.com/pershoot/KernelSU-Next/dev-susfs/kernel/setup.sh \
    | bash -s "$KSU_REF"
fi

KSU_KBUILD="$KERNEL_DIR/KernelSU-Next/kernel/Kbuild"
if [[ ! -f "$KSU_KBUILD" ]]; then
  echo "KernelSU-Next Kbuild was not integrated at $KSU_KBUILD" >&2
  exit 1
fi

# Restrict manager authorization to normal/spoofed ZSU APKs signed by the ZSU
# certificate. This prevents an unrelated KernelSU-Next manager from being
# crowned by a ZSU kernel.
ZSU_SIGNATURE="${ZSU_MANAGER_DER_LENGTH}:${ZSU_MANAGER_CERT_SHA256}"
if ! grep -q '^KSU_NEXT_MANAGER_LIST :=' "$KSU_KBUILD"; then
  echo "KernelSU-Next manager allowlist is missing" >&2
  exit 1
fi
sed -i "s|^KSU_NEXT_MANAGER_LIST := .*|KSU_NEXT_MANAGER_LIST := $ZSU_SIGNATURE|" "$KSU_KBUILD"
if grep -q '^KSU_NEXT_MANAGER_LIST := .*,' "$KSU_KBUILD"; then
  echo "Manager allowlist still contains multiple entries" >&2
  exit 1
fi

git clone --depth 1 --branch "$SUSFS_REF" "$SUSFS_REPO" "$ROOT_DIR/deps/susfs4ksu"
SUSFS_DIR="$ROOT_DIR/deps/susfs4ksu"
PATCH_FILE="$SUSFS_DIR/kernel_patches/50_add_susfs_in_gki-android12-5.10.patch"
if [[ ! -f "$PATCH_FILE" ]]; then
  echo "Missing SUSFS patch $PATCH_FILE" >&2
  exit 1
fi

# Apply the Android 12/5.10 patch once, then add the SUSFS source/header files.
if ! patch -p1 --dry-run < "$PATCH_FILE" >/dev/null 2>&1; then
  if ! grep -q 'CONFIG_KSU_SUSFS' fs/Makefile; then
    echo "SUSFS patch does not apply and no existing SUSFS marker was found" >&2
    exit 1
  fi
else
  patch -p1 < "$PATCH_FILE"
fi
cp -f "$SUSFS_DIR/kernel_patches/fs/susfs.c" fs/susfs.c
cp -f "$SUSFS_DIR/kernel_patches/include/linux/"* include/linux/

# The Android 15/6.6 export issue is harmless to fix here and keeps the source
# compatible if a shared SUSFS helper patch is selected later.
SELINUX_HIDE="$KERNEL_DIR/KernelSU-Next/kernel/feature/selinux_hide.c"
if [[ -f "$SELINUX_HIDE" ]]; then
  sed -i \
    -e 's/^static int security_context_to_sid_with_policy(/int security_context_to_sid_with_policy(/' \
    -e 's/^static int security_sid_to_context_with_policy(/int security_sid_to_context_with_policy(/' \
    -e 's/^static void \(__nocfi \)\?security_compute_av_user_with_policy(/void \1security_compute_av_user_with_policy(/' \
    "$SELINUX_HIDE"
fi

# Generate the platform blend and add only the explicit ZSU/SUSFS options.
export LLVM=1
export LLVM_IAS=1
scripts/gki/generate_defconfig.sh "$KERNEL_DEFCONFIG"
DEFCONFIG_PATH="arch/arm64/configs/$KERNEL_DEFCONFIG"

ensure_config() {
  local key="$1"
  local value="$2"
  sed -i "/^${key}=\|^# ${key} is not set$/d" "$DEFCONFIG_PATH"
  printf '%s=%s\n' "$key" "$value" >> "$DEFCONFIG_PATH"
}

ensure_config CONFIG_KSU y
ensure_config CONFIG_TMPFS_XATTR y
ensure_config CONFIG_TMPFS_POSIX_ACL y
ensure_config CONFIG_KSU_SUSFS y
ensure_config CONFIG_KSU_SUSFS_SUS_PATH y
ensure_config CONFIG_KSU_SUSFS_SUS_MOUNT y
ensure_config CONFIG_KSU_SUSFS_SUS_KSTAT y
ensure_config CONFIG_KSU_SUSFS_SPOOF_UNAME y
ensure_config CONFIG_KSU_SUSFS_ENABLE_LOG y
ensure_config CONFIG_KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS y
ensure_config CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG y
ensure_config CONFIG_KSU_SUSFS_OPEN_REDIRECT y
ensure_config CONFIG_KSU_SUSFS_SUS_MAP y

make O="$OUT_DIR" ARCH="$ARCH" LLVM=1 LLVM_IAS=1 \
  CROSS_COMPILE="$CROSS_COMPILE" CROSS_COMPILE_COMPAT="${CROSS_COMPILE_COMPAT:-arm-linux-gnueabihf-}" \
  "$KERNEL_DEFCONFIG"

make O="$OUT_DIR" ARCH="$ARCH" LLVM=1 LLVM_IAS=1 \
  CROSS_COMPILE="$CROSS_COMPILE" CROSS_COMPILE_COMPAT="${CROSS_COMPILE_COMPAT:-arm-linux-gnueabihf-}" \
  -j"${JOBS:-$(nproc)}" Image modules

IMAGE="$OUT_DIR/arch/arm64/boot/Image"
if [[ ! -s "$IMAGE" ]]; then
  echo "Kernel Image was not produced at $IMAGE" >&2
  exit 1
fi

mkdir -p "$ROOT_DIR/artifacts"
cp "$IMAGE" "$ROOT_DIR/artifacts/Image"
if [[ -f "$OUT_DIR/vmlinux" ]]; then cp "$OUT_DIR/vmlinux" "$ROOT_DIR/artifacts/vmlinux"; fi
if compgen -G "$OUT_DIR/**/*.ko" >/dev/null 2>&1; then
  find "$OUT_DIR" -name '*.ko' -type f -exec cp --parents {} "$ROOT_DIR/artifacts/" \;
fi

printf '%s\n' 'Kernel build completed.'
printf 'Image: %s bytes\n' "$(stat -c '%s' "$ROOT_DIR/artifacts/Image")"
