#!/usr/bin/env python3
"""
Extract device profile information from a stock boot.img, kernel.img, or Image.
Automatically extracts kernel version, sublevel, commit, release string,
compiler info, and version string, and optionally updates device-profiles.json.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

def find_linux_banner(data: bytes) -> str:
    """Find the 'Linux version ...' banner string in binary data."""
    # Pattern: Linux version 6.1.172-android14-...
    pattern = re.compile(rb"Linux version \d+\.\d+\.\d+-[^\x00\r\n]+")
    matches = pattern.findall(data)
    if matches:
        # Return the longest match decoded as utf-8 (ignore errors)
        best = max(matches, key=len)
        return best.decode("utf-8", errors="ignore")
    return ""

def decompress_kernel(kernel_path: str, temp_dir: str) -> str:
    """Decompress kernel if compressed with LZ4 or Gzip."""
    with open(kernel_path, "rb") as f:
        magic = f.read(4)

    # Legacy LZ4 magic: 0x184c2102 (little-endian: 02 21 4c 18)
    # Standard LZ4 frame magic: 0x184d2204 (little-endian: 04 22 4d 18)
    if magic in (b"\x02\x21\x4c\x18", b"\x04\x22\x4d\x18"):
        out_path = os.path.join(temp_dir, "Image_lz4_decompressed")
        cmd = ["lz4", "-d", "-q", "-f", kernel_path, out_path]
        try:
            subprocess.run(cmd, check=True)
            return out_path
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    # Gzip magic: 1f 8b
    if magic[:2] == b"\x1f\x8b":
        import gzip
        out_path = os.path.join(temp_dir, "Image_gz_decompressed")
        try:
            with gzip.open(kernel_path, "rb") as gz_in, open(out_path, "wb") as f_out:
                shutil.copyfileobj(gz_in, f_out)
            return out_path
        except Exception:
            pass

    return kernel_path

def extract_kernel_from_boot(boot_img_path: str, temp_dir: str) -> str:
    """Extract kernel from boot.img using avbroot or magiskboot."""
    # Try avbroot
    if shutil.which("avbroot"):
        kernel_out = os.path.join(temp_dir, "kernel.img")
        cmd = ["avbroot", "boot", "unpack", "--input", boot_img_path]
        try:
            subprocess.run(cmd, cwd=temp_dir, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(kernel_out):
                return kernel_out
        except subprocess.CalledProcessError:
            pass

    # Try magiskboot
    if shutil.which("magiskboot"):
        cmd = ["magiskboot", "unpack", boot_img_path]
        try:
            subprocess.run(cmd, cwd=temp_dir, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            kernel_out = os.path.join(temp_dir, "kernel")
            if os.path.exists(kernel_out):
                return kernel_out
        except subprocess.CalledProcessError:
            pass

    return ""

def parse_banner(banner: str) -> dict:
    """
    Parse a Linux banner string into device profile fields.
    Example:
    Linux version 6.1.172-android14-11-g87c0a9ca734b-ab16116086 (build-user@build-host)
    (Android (10087095, ...) clang version 17.0.2 (...), LLD 17.0.2) #1 SMP PREEMPT Wed Aug 19 01:40:20 UTC 2026
    """
    # Regex matching:
    # Linux version <ver>.<sublevel><release> (<user>@<host>) (<compiler>) <version_string>
    pattern = re.compile(
        r"^Linux version (?P<major>\d+)\.(?P<minor>\d+)\.(?P<sublevel>\d+)"
        r"(?P<release>-(?P<android_ver>android\d+)[^\s]*)\s+"
        r"\((?P<user>[^@]+)@(?P<host>[^)]+)\)\s+"
        r"\((?P<compiler>.*?)\)\s+"
        r"(?P<version_string>#\d+.*)$"
    )
    match = pattern.match(banner.strip())
    if not match:
        return {}

    d = match.groupdict()
    kernel_version = f"{d['major']}.{d['minor']}"
    sub_level = d['sublevel']
    android_version = d['android_ver']
    release = d['release']
    user = d['user']
    host = d['host']
    compiler = d['compiler']
    version_string = d['version_string']

    # Extract commit from release: -android14-11-g87c0a9ca734b-ab16116086 -> 87c0a9ca734b
    commit_match = re.search(r"-g([0-9a-fA-F]{7,40})", release)
    commit = commit_match.group(1) if commit_match else ""

    return {
        "kernel_version": kernel_version,
        "sub_level": sub_level,
        "android_version": android_version,
        "release": release,
        "commit": commit,
        "build_user": user,
        "build_host": host,
        "compiler_info": compiler,
        "version_string": version_string
    }

def main():
    parser = argparse.ArgumentParser(description="Extract device profile from stock kernel or boot.img")
    parser.add_argument("file", help="Path to boot.img, kernel.img, or Image")
    parser.add_argument("--update", metavar="CODENAME", help="Update device-profiles.json for given codename")
    parser.add_argument("--name", help="Device human-readable name (used when creating a new profile entry)")
    parser.add_argument("--spl", default="2026-06", help="OS patch level string (e.g. 2026-06)")
    parser.add_argument("--json", action="store_true", help="Print JSON snippet only")

    args = parser.parse_args()

    if not os.path.isfile(args.file):
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    temp_dir = tempfile.mkdtemp(prefix="kernel_extract_")
    try:
        kernel_file = args.file
        # Check if file is boot.img (starts with ANDR or AVB)
        with open(args.file, "rb") as f:
            head = f.read(8)

        if head.startswith(b"ANDROID!") or head.startswith(b"AVB0"):
            extracted = extract_kernel_from_boot(args.file, temp_dir)
            if extracted:
                kernel_file = extracted

        # Decompress if needed
        uncompressed_path = decompress_kernel(kernel_file, temp_dir)

        with open(uncompressed_path, "rb") as f:
            data = f.read()

        banner = find_linux_banner(data)
        if not banner:
            print("Error: Could not find 'Linux version' banner in kernel binary.", file=sys.stderr)
            sys.exit(1)

        info = parse_banner(banner)
        if not info:
            print(f"Found banner but failed to parse regex:\n{banner}", file=sys.stderr)
            sys.exit(1)

        if args.json:
            print(json.dumps(info, indent=2))
            return

        print("=" * 60)
        print(" EXTRACTED KERNEL INFORMATION")
        print("=" * 60)
        print(f"Banner:         {banner}")
        print(f"Kernel Version: {info['kernel_version']}.{info['sub_level']}")
        print(f"Android:        {info['android_version']}")
        print(f"Commit SHA:     {info['commit']}")
        print(f"Release Suffix: {info['release']}")
        print(f"Build User:     {info['build_user']}@{info['build_host']}")
        print(f"Version String: {info['version_string']}")
        print("=" * 60)

        if args.update:
            codename = args.update
            repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            profiles_file = os.path.join(repo_root, "device-profiles.json")

            if not os.path.exists(profiles_file):
                print(f"Error: {profiles_file} not found.", file=sys.stderr)
                sys.exit(1)

            with open(profiles_file, "r") as f:
                data = json.load(f)

            if codename not in data.get("devices", {}):
                dev_entry = {
                    "name": args.name or codename.capitalize(),
                    "codename": codename,
                    "android_version": info["android_version"],
                    "kernel_version": info["kernel_version"],
                    "sub_level": info["sub_level"],
                    "os_patch_level": args.spl,
                    "commit": info["commit"],
                    "stock_kernel": {
                        "release": info["release"],
                        "version_string": info["version_string"],
                        "build_user": info["build_user"],
                        "build_host": info["build_host"],
                        "compiler_info": info["compiler_info"]
                    }
                }
                data.setdefault("devices", {})[codename] = dev_entry
            else:
                entry = data["devices"][codename]
                entry["android_version"] = info["android_version"]
                entry["kernel_version"] = info["kernel_version"]
                entry["sub_level"] = info["sub_level"]
                entry["commit"] = info["commit"]
                if args.spl:
                    entry["os_patch_level"] = args.spl
                entry.setdefault("stock_kernel", {})
                entry["stock_kernel"]["release"] = info["release"]
                entry["stock_kernel"]["version_string"] = info["version_string"]
                entry["stock_kernel"]["build_user"] = info["build_user"]
                entry["stock_kernel"]["build_host"] = info["build_host"]
                entry["stock_kernel"]["compiler_info"] = info["compiler_info"]

            with open(profiles_file, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")

            print(f"Successfully updated device profile '{codename}' in {profiles_file}")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    main()
