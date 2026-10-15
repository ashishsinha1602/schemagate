#!/bin/bash -eu
# Dependencies by hash (scripts/lock_ci.py writes the file), schemagate itself
# as a wheel with --no-deps, then one fuzzer per fuzz/fuzz_*.py.
pip3 install --require-hashes -r .clusterfuzzlite/requirements.txt
pip3 wheel --no-deps -w /tmp/sgwheel .
pip3 install --no-deps /tmp/sgwheel/*.whl
for fuzzer in fuzz/fuzz_*.py; do
  compile_python_fuzzer "$fuzzer"
done
