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
export CC="${CC:-clang}"
export HOSTCC="${HOSTCC:-clang}"
export HOSTLD="${HOSTLD:-ld.lld}"
export HOSTAR="${HOSTAR:-llvm-ar}"
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
# common-style GKI trees and ordinary Qualcomm kernel trees. The legacy-susfs
# tag is pinned in device.env because the moving dev-susfs head is not compatible
# with this vendor tree's Linux 5.4 SELinux internals.
if [[ ! -d KernelSU-Next ]]; then
  curl -fsSL "${KSU_SETUP_URL:-https://raw.githubusercontent.com/KernelSU-Next/KernelSU-Next/dev-susfs/kernel/setup.sh}" \
    | bash -s "$KSU_REF"
fi

KSU_ROOT="$KERNEL_DIR/KernelSU-Next/kernel"
KSU_KBUILD="$KSU_ROOT/Kbuild"
if [[ ! -f "$KSU_KBUILD" ]]; then
  echo "KernelSU-Next Kbuild was not integrated at $KSU_KBUILD" >&2
  exit 1
fi

# Restrict manager authorization to normal/spoofed ZSU APKs signed by the ZSU
# certificate. Newer builds use a comma-separated KSU_NEXT_MANAGER_LIST; the
# legacy-susfs tag uses the equivalent size/hash pair in Kbuild.
ZSU_SIGNATURE="${ZSU_MANAGER_DER_LENGTH}:${ZSU_MANAGER_CERT_SHA256}"
if grep -q '^KSU_NEXT_MANAGER_LIST :=' "$KSU_KBUILD"; then
  sed -i "s|^KSU_NEXT_MANAGER_LIST := .*|KSU_NEXT_MANAGER_LIST := $ZSU_SIGNATURE|" "$KSU_KBUILD"
  if grep -q '^KSU_NEXT_MANAGER_LIST := .*,' "$KSU_KBUILD"; then
    echo "Manager allowlist still contains multiple entries" >&2
    exit 1
  fi
elif grep -qE '^KSU_NEXT_MANAGER_(SIZE|HASH) :=' "$KSU_KBUILD"; then
  sed -i \
    -e "s|^KSU_NEXT_MANAGER_SIZE := .*|KSU_NEXT_MANAGER_SIZE := ${ZSU_MANAGER_DER_LENGTH}|" \
    -e "s|^KSU_NEXT_MANAGER_HASH := .*|KSU_NEXT_MANAGER_HASH := ${ZSU_MANAGER_CERT_SHA256}|" \
    "$KSU_KBUILD"
else
  echo "KernelSU-Next manager certificate contract is missing" >&2
  exit 1
fi
if grep -q '^KSU_NEXT_MANAGER_LIST :=' "$KSU_KBUILD"; then
  grep -q "$ZSU_SIGNATURE" "$KSU_KBUILD"
elif grep -q '^KSU_NEXT_MANAGER_SIZE :=' "$KSU_KBUILD"; then
  grep -q "^KSU_NEXT_MANAGER_SIZE := ${ZSU_MANAGER_DER_LENGTH}$" "$KSU_KBUILD"
  grep -q "^KSU_NEXT_MANAGER_HASH := ${ZSU_MANAGER_CERT_SHA256}$" "$KSU_KBUILD"
else
  echo "ZSU manager certificate was not injected into KernelSU-Next" >&2
  exit 1
fi

SUSFS_DIR="$ROOT_DIR/deps/susfs4ksu"
if [[ ! -d "$SUSFS_DIR/.git" ]]; then
  git clone --depth 1 --branch "$SUSFS_REF" "$SUSFS_REPO" "$SUSFS_DIR"
fi
SUSFS_API_DIR="$ROOT_DIR/deps/susfs4ksu-api"
if [[ ! -d "$SUSFS_API_DIR/.git" ]]; then
  git clone --depth 1 --branch "${SUSFS_API_REF:-$SUSFS_REF}" "$SUSFS_REPO" "$SUSFS_API_DIR"
fi
PATCH_FILE="$SUSFS_DIR/${SUSFS_PATCH:-kernel_patches/50_add_susfs_in_kernel-5.4.patch}"
if [[ ! -f "$PATCH_FILE" ]]; then
  echo "Missing SUSFS patch $PATCH_FILE" >&2
  exit 1
fi

# Resolve the one known vendor-source conflict before patching. Fail closed
# if the downloaded source contains any different conflict layout.
python3 "$ROOT_DIR/scripts/clean_vendor_conflicts.py" "$KERNEL_DIR/drivers/rtc/rtc-pm8xxx.c"

# Apply the kernel-5.4 patch with a bounded fuzz level. The NX669J vendor
# tree is a downstream 5.4.147 variant, so its surrounding context differs
# slightly from the upstream SUSFS reference tree.
PATCH_LOG="$OUT_DIR/susfs-patch.log"
rm -f "$PATCH_LOG"
PATCH_STATUS=0
patch --batch --forward --fuzz=3 -p1 < "$PATCH_FILE" >"$PATCH_LOG" 2>&1 || PATCH_STATUS=$?
if [[ "$PATCH_STATUS" -ne 0 && "${SUSFS_NEEDS_FD_PORT:-false}" != true ]]; then
  cat "$PATCH_LOG" >&2
  echo "SUSFS kernel-5.4 patch cannot be applied to this source" >&2
  exit 1
fi

# This source tree has a different fs/proc/fd.c body than the SUSFS reference
# tree. Port the one rejected hunk explicitly and keep the port reviewable.
if [[ "${SUSFS_NEEDS_FD_PORT:-false}" == true ]]; then
  python3 "$ROOT_DIR/scripts/port_fd_susfs.py" "$KERNEL_DIR/fs/proc/fd.c"
  rm -f "$KERNEL_DIR/fs/proc/fd.c.rej"
fi
if [[ -f "$KERNEL_DIR/fs/notify/fdinfo.c" ]]; then
  python3 "$ROOT_DIR/scripts/port_inotify_susfs.py" "$KERNEL_DIR/fs/notify/fdinfo.c"
fi
if [[ "${SUSFS_HAS_PROC_BOOTCONFIG:-true}" != true ]]; then
  if [[ ! -f "$KERNEL_DIR/fs/proc/cmdline.c" ]]; then
    echo "NX669J source has neither fs/proc/bootconfig.c nor fs/proc/cmdline.c" >&2
    exit 1
  fi
  python3 "$ROOT_DIR/scripts/port_cmdline_susfs.py" "$KERNEL_DIR/fs/proc/cmdline.c"
fi

# The kernel-5.4 branch supplies the source-tree patch, while the v2.2 API
# implementation comes from the Android 12/5.10 branch. KernelSU-Next
# v3.1.0-legacy-susfs calls this v2.x API directly.
for payload in fs/susfs.c include/linux/susfs.h include/linux/susfs_def.h; do
  if [[ ! -f "$SUSFS_API_DIR/kernel_patches/$payload" ]]; then
    echo "Missing SUSFS v2.2 payload: $SUSFS_API_DIR/kernel_patches/$payload" >&2
    exit 1
  fi
done
cp -f "$SUSFS_API_DIR/kernel_patches/fs/susfs.c" fs/susfs.c
cp -f "$SUSFS_API_DIR/kernel_patches/include/linux/susfs.h" include/linux/susfs.h
cp -f "$SUSFS_API_DIR/kernel_patches/include/linux/susfs_def.h" include/linux/susfs_def.h
# The v2.2 payload is authored for a 5.10 fsnotify_ops layout. NX669J's
# vendor kernel is 5.4, where the callback field is handle_event and uses
# the older eight-argument ABI.
python3 "$ROOT_DIR/scripts/port_susfs_54_defs.py" "$KERNEL_DIR/include/linux/susfs_def.h"
python3 "$ROOT_DIR/scripts/port_susfs_fsnotify.py" "$KERNEL_DIR/fs/susfs.c"
if [[ -f "$SUSFS_DIR/kernel_patches/fs/sus_su.c" ]]; then
  cp -f "$SUSFS_DIR/kernel_patches/fs/sus_su.c" fs/sus_su.c
fi
find "$KERNEL_DIR" -name '*.orig' -delete
if find "$KERNEL_DIR" -name '*.rej' -print -quit | grep -q .; then
  echo "Unexpected SUSFS reject file remains" >&2
  find "$KERNEL_DIR" -name '*.rej' -print >&2
  exit 1
fi

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

# This vendor 5.4 VDSO32 Makefile forces clang through an external assembler.
# On current Ubuntu runners that path can resolve host /usr/bin/as and reject
# ARM's -EL flag. Use the installed arm-linux-gnueabihf GCC compat compiler
# only for VDSO32; the main kernel remains clang/LLVM.
VDSO32_MAKE="$KERNEL_DIR/arch/arm64/kernel/vdso32/Makefile"
if [[ -f "$VDSO32_MAKE" ]]; then
  sed -i \
    -e 's/^CC_COMPAT ?= $(CC)$/CC_COMPAT := $(CROSS_COMPILE_COMPAT)gcc/' \
    -e '/^CC_COMPAT += $(CC_COMPAT_CLANG_FLAGS)$/d' \
    "$VDSO32_MAKE"
fi

# Generate the platform blend and add only the explicit ZSU/SUSFS options.
export LLVM=1
export LLVM_IAS=1
# The vendor 5.4 tree predates modern warning cleanup. Keep warnings visible,
# but prevent known legacy-driver warnings from aborting an otherwise valid
# clang build. Do not disable general diagnostics or incompatible-pointer errors.
VENDOR_WARN_FLAGS="${KCFLAGS:-} -Wno-unused-but-set-variable -Wno-error=unused-but-set-variable -Wno-strict-prototypes -Wno-error=strict-prototypes -Wno-implicit-int -Wno-error=implicit-int"
export KCFLAGS="$VENDOR_WARN_FLAGS"
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
# The device is non-GKI and uses /proc/cmdline; port_cmdline_susfs.py provides
# the corresponding hook when fs/proc/bootconfig.c is absent.

if [[ -x build/build.sh && -f common/build.config.gki.aarch64 ]]; then
  echo "Detected synced common/ build tree; using Android build.sh entrypoint."
  LTO=thin BUILD_CONFIG=common/build.config.gki.aarch64 DISABLE_WRAPPER=1 \
    KCFLAGS="$VENDOR_WARN_FLAGS" build/build.sh CC="${CC:-clang}" LLVM=1 LLVM_IAS=1 \
    CROSS_COMPILE="$CROSS_COMPILE" CROSS_COMPILE_COMPAT="${CROSS_COMPILE_COMPAT:-arm-linux-gnueabihf-}"
  IMAGE="$(find "$KERNEL_DIR/out" -type f -path '*/dist/Image' -print -quit)"
else
  echo "Using direct make fallback for the single-repository NX669J 5.4.147 source clone."
  make O="$OUT_DIR" ARCH="$ARCH" LLVM=1 LLVM_IAS=1 LTO=thin DISABLE_WRAPPER=1 \
    KCFLAGS="$VENDOR_WARN_FLAGS" CROSS_COMPILE="$CROSS_COMPILE" \
    CROSS_COMPILE_COMPAT="${CROSS_COMPILE_COMPAT:-arm-linux-gnueabihf-}" \
    "$KERNEL_DEFCONFIG"

  make O="$OUT_DIR" ARCH="$ARCH" LLVM=1 LLVM_IAS=1 LTO=thin DISABLE_WRAPPER=1 \
    KCFLAGS="$VENDOR_WARN_FLAGS" CROSS_COMPILE="$CROSS_COMPILE" \
    CROSS_COMPILE_COMPAT="${CROSS_COMPILE_COMPAT:-arm-linux-gnueabihf-}" \
    -j"${JOBS:-$(nproc)}" Image
  IMAGE="$OUT_DIR/arch/arm64/boot/Image"
fi
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
