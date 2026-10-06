#!/bin/bash
# Re-apply the blue-hydra Ruby compatibility fix if it has been lost.
#
# Why this exists
# ---------------
# blue-hydra 1.9.21-0kali1 vendors data_objects 0.10.17, which references the
# constant Fixnum. Ruby removed Fixnum in 3.2; this box runs Ruby 3.3.8. The
# reference is on a live line, so DataMapper.auto_upgrade! raises NameError and
# the service exits 1 immediately.
#
# The package hides the real cause: blue_hydra.rb has a bare `rescue NameError`
# that prints a canned "data_objects is not compatible with your version of
# ruby" message regardless of what actually raised. The genuine fault was only
# visible after replacing that rescue with a trap.
#
# The fix is one line, in one vendored gem:
#   data_objects-0.10.17/lib/data_objects/pooling.rb:149
#   unless Fixnum === max_size   ->   unless Integer === max_size
# It is the same substitution the package's own message points at
# (data_objects-fixnum2integer.patch), applied to the only live reference;
# the other 12 matches in the bundle are comments and rspec files.
#
# Why a re-apply unit
# -------------------
# That gem lives under /usr/share, owned by dpkg. `apt upgrade blue-hydra` will
# restore the original file and silently break the service again. This unit
# re-checks at boot, repairs if needed, and fails loudly if it cannot - rather
# than leaving a service that looks enabled and refuses to start.

set -euo pipefail

GEM_POOLING="/usr/share/blue-hydra/vendor/bundle/ruby/3.3.0/gems/data_objects-0.10.17/lib/data_objects/pooling.rb"

if [ ! -f "$GEM_POOLING" ]; then
    echo "blue-hydra-ruby-fix: $GEM_POOLING not found; nothing to do" >&2
    exit 0
fi

if grep -q 'unless Integer === max_size' "$GEM_POOLING"; then
    echo "blue-hydra-ruby-fix: already applied"
    exit 0
fi

if ! grep -q 'unless Fixnum === max_size' "$GEM_POOLING"; then
    echo "blue-hydra-ruby-fix: neither Fixnum nor Integer found at the expected line; refusing to guess" >&2
    exit 1
fi

cp -n "$GEM_POOLING" "$GEM_POOLING.fixnum-backup"
sed -i 's/unless Fixnum === max_size/unless Integer === max_size/' "$GEM_POOLING"
ruby -c "$GEM_POOLING" >/dev/null
echo "blue-hydra-ruby-fix: applied (Fixnum -> Integer) and syntax-checked"
