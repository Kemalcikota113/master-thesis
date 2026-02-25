## Dataset reference guide

This MarkDown file showcases how to run each raw dataset in `datasets-c/raw-data` to verify original repository health before cleaning and translation.

## sds-master

### Prerequisites:

* `gcc` (or compatible C compiler available as `cc`)
* `make`

### Commands:

1. `cd datasets-c/raw-data/sds-master`
2. `make clean && make`
3. `./sds-test`

### Verification:

* Expected final line: `46 tests, 46 passed, 0 failed`

## cJSON

### Prerequisites:

* `gcc` (or compatible C compiler available as `cc`)
* `make`

### Commands:

1. `cd datasets-c/raw-data/cJSON-master`
2. `make clean && make`
3. `make test`

### Verification:

* Test binary runs without errors and prints JSON output
* Command exits successfully (exit code `0`)

## http-parser-main

### Prerequisites:

* `gcc` (or compatible C compiler available as `cc`)
* `make`

### Commands:

1. `cd datasets-c/raw-data/http-parser-main`
2. `make clean && make test`

### Verification:

* Both test binaries (`test_g`, `test_fast`) run successfully
* Output contains `requests okay` and `responses okay`

## kilo-master

### Prerequisites:

* `gcc` (or compatible C compiler available as `cc`)
* `make`

### Commands:

1. `cd datasets-c/raw-data/kilo-master`
2. `make`

### Verification:

* Binary `kilo` is produced
* Build command exits successfully (exit code `0`)
