# NX669J ZSU SUSFS Kernel

This private repository builds a device-native custom kernel for the Nubia RedMagic 6 / NX669J on Android 12, using the Snapdragon 888 Lahaina QGKI source tree with KernelSU-Next and SUSFS integration for the ZSU manager.

The target device information currently recorded for this project is:

| Property | Value |
| --- | --- |
| Device | Nubia RedMagic 6 / NX669J |
| Hardware | NX669J_V1AMB |
| ROM | REDMAGIC OS 5.5 |
| Android | 12 |
| SoC | Qualcomm Snapdragon 888 / Lahaina |
| Stock kernel family | 5.4.147 QGKI |
| Stock kernel release | `5.4.147-qgki-gd9147d4b1b39` |
| Target defconfig | `vendor/lahaina-qgki_defconfig` |
| Kernel image | `arch/arm64/boot/Image` |
| Boot layout reference | Recovery-as-boot / header v3 device-tree configuration |

The stock boot image reports `5.4.147-qgki-gd9147d4b1b39`, and the target defconfig enables `CONFIG_MODVERSIONS`. The build therefore pins `CONFIG_LOCALVERSION` to that stock release and disables automatic Git/`-dirty` suffixes; CI checks both `kernel.release` and the release string embedded in `Image`. This aligns module vermagic only—it does not prove all vendor symbol CRCs match, bypass AVB, or replace exact-device boot testing.

The kernel source is cloned during CI from [`tangalbert919/android_kernel_nubia_sm8350`](https://github.com/tangalbert919/android_kernel_nubia_sm8350), branch `rebase-17200-a12`. Because this device tree is **5.4.147 rather than GKI 5.10**, the workflow uses the `kernel-5.4` branch from [`simonpunk/susfs4ksu`](https://gitlab.com/simonpunk/susfs4ksu) and applies `50_add_susfs_in_kernel-5.4.patch` with a bounded context fuzz level. The small downstream differences are handled explicitly: `fs/proc/fd.c` receives a reviewed mount-hiding port, and the non-GKI `fs/proc/cmdline.c` receives the corresponding spoofing hook because this source has no `fs/proc/bootconfig.c`. KernelSU-Next is pinned to the upstream [`v3.1.0-legacy-susfs`](https://github.com/KernelSU-Next/KernelSU-Next/tree/v3.1.0-legacy-susfs) tag. This legacy SUSFS tag is used intentionally: the moving `dev-susfs` head currently assumes newer SELinux and scheduler internals and does not compile against this vendor 5.4.147 tree.

ZSU authorization is certificate-bound. The workflow replaces the upstream manager allowlist with the ZSU certificate currently used by the published normal and spoofed ZSU managers:

```text
DER length: 0x318
SHA-256: ba1159a5819dec96cdcb2498bef73170b0ba1735c12139bde1b7677bf7c5c2ab
```

The workflow produces a kernel `Image`, a flashable AnyKernel3 ZIP, and an attempted `kernelsu.ko` LKM artifact when the source configuration supports module output. The boot image itself is not generated from an unknown stock image in CI. A device-specific `boot.img` must be supplied separately for repacking, AVB handling, and final device testing.

## Build workflow

Run **Build NX669J ZSU SUSFS Kernel** from the Actions tab. The default build enables the device-native QGKI defconfig, SUSFS, and ZSU certificate authorization. The workflow fails closed if the source, defconfig, SUSFS patch, KernelSU integration, or artifact checks do not match expectations.

The build is not considered device-verified until the resulting AnyKernel ZIP has been tested on the exact NX669J V7.04 software build with a recovery path available. Earlier CI attempts exposed two incompatibilities: the initial 5.10 SUSFS patch did not match the 5.4.147 source, and the moving KernelSU-Next `dev-susfs` head used newer SELinux/scheduler APIs. The repository now uses the kernel-5.4 patch, explicit downstream ports, and the pinned legacy-susfs KernelSU-Next tag described above. Do not flash an artifact intended for another device, boot layout, or kernel family.

## Safety

A kernel build can cause a boot loop or data-loss risk if the wrong image, slot, DTB, AVB metadata, or vendor modules are used. Keep untouched stock `boot_a`, `boot_b`, `vendor_boot`, `dtbo`, and recovery images before testing. Test one artifact at a time and keep fastboot access available.
