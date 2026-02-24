## Dataset reference guide

This MarkDown file showcases how to run each of the datasets in the `datasets-c` folder in order to verify that the projects are healthy and running properly before using the `c2rust` pipeline to translate to Rust and run the APR agent.

## sds-master

### Prerequisites:

* `gcc` (or compatible C compiler available as `cc`)
* `make`

### Commands:

1. `cd datasets-c/sds-master`
2. `make clean && make`
3. `./sds-test`

### Verification:

* Expected final line: `46 tests, 46 passed, 0 failed`

## cJSON

### Prerequisites:

* `gcc` (or compatible C compiler available as `cc`)
* `make`

### Commands:

1. `cd datasets-c/cjson/cJSON-master`
2. `make clean && make`
3. `make test`

### Verification:

* Test binary runs without errors and prints JSON output
* Command exits successfully (exit code `0`)
