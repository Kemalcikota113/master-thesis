## Cleaning documentation

Since some codebases that i pull from github sometimes include files not necessarily in C, like for example documenation in .txt or .md format or even already compiled .c files and test suites, i have to shave of some of that data when being fed to the initial translation agent. This document right here will include all of the steps taken when cleaning the repos up to ensure scientific integrity and generalizability.

### sds-master

* **Removed Files:**
 * `sds-test` (compiled binary artifact)

* **Kept Files (cleaned set):**
 * `sds.c`
 * `sds.h`
 * `sdsalloc.h`
 * `testhelp.h`
 * `Makefile`, `LICENSE`, `README.md`, `Changelog`, `.gitignore`

* **Cleaning rationale:**
 * Removed generated executable to avoid dataset contamination from build artifacts.
 * Kept source and headers used by translation plus minimal project metadata.

### cJSON-master

* **Removed Files:**
 * `test.c`
 * `tests/` (all test suites and fixtures)
 * `fuzzing/` (all fuzz harnesses and inputs)
 * `library_config/`
 * build artifacts: `cJSON_test`, `*.o`, `*.a`, `*.so*`
 * non-essential project files: `CMakeLists.txt`, `Makefile`, `valgrind.supp`, `appveyor.yml`, `SECURITY.md`, `CONTRIBUTORS.md`, `CHANGELOG.md`

* **Kept Files (cleaned set):**
 * `cJSON.c`
 * `cJSON.h`
 * `cJSON_Utils.c`
 * `cJSON_Utils.h`
 * `LICENSE`, `README.md`

* **Cleaning rationale:**
 * Removed test/fuzz/build-system noise so translation focuses on core library implementation.
 * Removed compiled outputs to prevent non-source artifacts from influencing the pipeline.
 * Preserved only core C source/header files needed for file-by-file C -> Rust translation.

### http-parser-main

* **Removed Files:**
 * `test.c`
 * `bench.c`
 * `contrib/`
 * `fuzzers/`
 * build/config metadata: `Makefile`, `http_parser.gyp`, `.travis.yml`, `.mailmap`, `.gitignore`, `AUTHORS`

* **Kept Files (cleaned set):**
 * `http_parser.c`
 * `http_parser.h`
 * `LICENSE-MIT`, `README.md`

* **Cleaning rationale:**
 * Removed benchmark/test/fuzz files to keep translation input focused on core parser implementation.
 * Removed build-system and CI metadata not required for file-level translation.

### kilo-master

* **Removed Files:**
 * `Makefile`
 * `TODO`
 * `.gitignore`

* **Kept Files (cleaned set):**
 * `kilo.c`
 * `LICENSE`, `README.md`

* **Cleaning rationale:**
 * Preserved the single core source file and minimal metadata.
 * Removed auxiliary project files that do not improve translation context.
