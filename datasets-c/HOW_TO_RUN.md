## Dataset reference guide

This MarkDown file showcases how to validate the cleaned datasets in `datasets-c` before using the `c2rust` pipeline.

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

Note: cleaned cJSON contains only core source/header files for translation quality, so verification here is compile-only.

### Prerequisites:

* `gcc` (or compatible C compiler available as `cc`)
* `make`

### Commands:

1. `cd datasets-c/cjson/cJSON-master`
2. `cc -std=c99 -Wall -Wextra -pedantic -c cJSON.c cJSON_Utils.c`

### Verification:

* Command exits successfully (exit code `0`)
* Object files are produced: `cJSON.o`, `cJSON_Utils.o`

## http-parser-main

Note: cleaned http-parser contains core parser source/header files only, so verification here is compile-only.

### Prerequisites:

* `gcc` (or compatible C compiler available as `cc`)

### Commands:

1. `cd datasets-c/http-parser-main`
2. `cc -std=c99 -Wall -Wextra -Werror -c http_parser.c`

### Verification:

* Command exits successfully (exit code `0`)
* Object file is produced: `http_parser.o`

## kilo-master

Note: cleaned kilo contains core source file only, so verification here is compile-only.

### Prerequisites:

* `gcc` (or compatible C compiler available as `cc`)

### Commands:

1. `cd datasets-c/kilo-master`
2. `cc -std=c99 -Wall -W -pedantic -c kilo.c`

### Verification:

* Command exits successfully (exit code `0`)
* Object file is produced: `kilo.o`
