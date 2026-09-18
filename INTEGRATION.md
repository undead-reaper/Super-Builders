# Kernel Integration & Flashing Guide

This guide covers how to take the built kernel artifacts from this repository and flash or integrate them into your device.

---

## Overview of Artifacts

Each successful build produces an **AnyKernel3** zip package (e.g., `6.1.172-android14-2026-06-KernelSU-Next-AnyKernel3.zip`).

Inside the AnyKernel3 zip, you will find:
- `Image`: The raw, compiled ARM64 Linux kernel binary (GKI).
- `anykernel.sh` and helper scripts: Logic for unpacking your device's existing boot partition, replacing the kernel binary, and repacking on-device.

Depending on your device setup, choose the appropriate workflow below:
1. **[Traditional Recovery (TWRP / OrangeFox)](#method-1-custom-recovery-twrp--orangefox)**: Unlocked bootloader with a custom recovery.
2. **[avbroot with Custom AVB Key](#method-2-avbroot-with-custom-avb-key)**: Locked bootloader or verified boot setup with custom signing keys.
3. **[Manual Fastboot Flashing](#method-3-manual-bootimg-repack--fastboot)**: Unlocked bootloader using `fastboot flash boot`.

---

## Method 1: Custom Recovery (TWRP / OrangeFox)

If your device has an unlocked bootloader and a custom recovery installed:

1. Download the AnyKernel3 zip from the GitHub Actions Artifacts section.
2. Copy the zip file to your device's internal storage or USB OTG.
3. Reboot to recovery mode.
4. Select **Install** → choose the AnyKernel3 zip → Swipe to flash.
5. Reboot system.

---

## Method 2: avbroot with Custom AVB Key

If you use **[avbroot](https://github.com/chenxiaolong/avbroot)** to sign firmware with a custom AVB (Android Verified Boot) key (e.g., to preserve a locked bootloader):

> [!NOTE]
> AnyKernel3 zips are designed for custom recoveries and cannot be flashed directly by `avbroot`. Instead, extract the raw `Image` binary and pack it into your device's `boot.img`.

### Step 1: Extract the Kernel Binary (`Image`)

Unzip the AnyKernel3 zip to retrieve the raw kernel binary:

```bash
unzip 6.1.172-android14-2026-06-KernelSU-Next-AnyKernel3.zip Image
```

### Step 2: Unpack Stock `boot.img`

Obtain the stock `boot.img` matching your current OS build (extracted from your stock full OTA or firmware dump).

Unpack the boot image using `avbroot`:

```bash
avbroot boot unpack --input boot.img
```

This generates `boot.toml`, `kernel.img`, and `ramdisk.img.*` in your working directory.

### Step 3: Replace Kernel & Repack

1. Replace `kernel.img` with your compiled `Image`:
   ```bash
   cp -f Image kernel.img
   ```

2. Repack the boot image:
   ```bash
   avbroot boot pack --output boot_custom.img
   ```

---

### Step 4: Sign & Flash

#### Option A: Full OTA Patching (`avbroot ota patch`) — Recommended

If you update your system using full OTA packages:

Since KernelSU / SUSFS is built directly into the kernel, you do not need Magisk. Provide the customized boot image via `--prepatched`:

```bash
avbroot ota patch \
  --input <stock_ota.zip> \
  --output <patched_ota.zip> \
  --key-avb <path/to/avb_private_key.key> \
  --key-ota <path/to/ota_private_key.key> \
  --cert-ota <path/to/ota_cert.crt> \
  --prepatched boot_custom.img
```

Then sideload `<patched_ota.zip>` from stock recovery:

```bash
adb sideload <patched_ota.zip>
```

---

#### Option B: Standalone Boot Image Signing (Fastboot)

If your device setup allows flashing individual signed partitions via fastboot:

1. Sign the repacked boot image with your AVB key:
   ```bash
   avbroot avb repack \
     --input boot_custom.img \
     --output boot_signed.img \
     --key <path/to/avb_private_key.key>
   ```

2. Flash the signed boot image:
   ```bash
   fastboot flash boot boot_signed.img
   fastboot reboot
   ```

---

## Method 3: Manual Boot Image Repack (Fastboot, Unlocked)

If your bootloader is unlocked and you don't have TWRP:

1. Extract `Image` from the AnyKernel3 zip.
2. Unpack your stock `boot.img` using `magiskboot` or `avbroot boot unpack`:
   ```bash
   magiskboot unpack boot.img
   ```
3. Replace `kernel` with `Image`:
   ```bash
   cp -f Image kernel
   magiskboot repack boot.img boot_custom.img
   ```
4. Flash via fastboot:
   ```bash
   fastboot flash boot boot_custom.img
   fastboot reboot
   ```

---

## Post-Boot Setup

Once the system boots:

1. **Install the Manager Application**:
   - **KernelSU-Next**: Download the latest APK from [KernelSU-Next Releases](https://github.com/KernelSU-Next/KernelSU-Next/releases).
   - **SukiSU-Ultra**: Download from [SukiSU-Ultra Releases](https://github.com/SukiSU-Ultra/SukiSU-Ultra/releases).
   - **ReSukiSU**: Download from [ReSukiSU Releases](https://github.com/ReSukiSU/ReSukiSU/releases).
   - **WildKSU**: Download from [WildKernels/Wild_KSU Releases](https://github.com/WildKernels/Wild_KSU/releases).

2. **Verify Root & Features**:
   - Open the manager app. It should display **Working** along with your kernel version.
   - For SUSFS: Check the manager's module / hide status or run `ksu_susfs` CLI tools to verify SUSFS hiding.
   - For ZRAM: Check active compression algorithms via:
     ```bash
     cat /sys/block/zram0/comp_algorithm
     ```
     Ensure `lz4kd` or your preferred compressor is selected.
