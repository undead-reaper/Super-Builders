#!/bin/bash
# Runs BEFORE patch application — only fix vanilla kernel issues here
# Post-patch fixes (show_pad, etc.) are in each build workflow
set -euo pipefail

KERNEL_COMMON="$1"
SUBLEVEL="$2"

cd "$KERNEL_COMMON" || exit 1

# In 6.1.157+, <trace/hooks/blk.h> was added to fs/namespace.c right before "pnode.h",
# which breaks 50_ and 51_ patch context matching.
# Move it before <linux/fs_context.h> so the context matches cleanly.
if [[ -f fs/namespace.c ]] && grep -q 'trace/hooks/blk\.h' fs/namespace.c; then
    sed -i '/#include <trace\/hooks\/blk\.h>/d' fs/namespace.c
    sed -i '/#include <linux\/fs_context\.h>/i #include <trace/hooks/blk.h>' fs/namespace.c
fi
