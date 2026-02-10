## TASK 1 - Find datasets

* https://github.com/tastejs/todomvc/tree/master/examples/javascript-es6

* https://github.com/krausest/js-framework-benchmark/tree/master/frameworks/keyed/vanillajs

* https://github.com/mits-gossau/event-driven-web-components-realworld-example-app

## TASK 2 - Find some good evaluator metrics

I think im gonna use functional testing to ensure that the app actually behaves as expected from the translator like playwright, cypress or selenium

these are some of the metrics i can derive from the actual feedback loop and compiler, linter.

* Repair Success Rate: The percentage of code chunks (or assembled components) that successfully move from an "Error" state to a "Green" (compiling) state.

* Error Reduction Factor (ERF): The ratio of initial errors to final errors. If a component starts with 15 TypeScript errors and the APRA reduces it to 2, your ERF is 0.86.

* Mean Iterations to Repair (MITR): The average number of feedback loops (compiler -> agent -> fix) required to reach a green state. This measures the efficiency of your prompt engineering.

* Token Efficiency: In an industrial setting like Softwerk, cost matters. Tracking how many tokens are used per "fixed" error is a great metric for the "Engineering" side of your degree.

i can use some hard truth metrics as well since im not using datasets with ground truth:

* Compilation Rate (CR): The % of projects that pass vue-tsc without any --skipLibCheck hacks.

* Lint Compliance Score: Using a standard Vue 3 ESLint config, what percentage of the generated code is "clean"?

* Type Coverage: The percentage of variables that have an explicit type vs. those left as any. A higher percentage indicates a "smarter" translation.

## TASK 3 - Read up/find sme good code translation/APR papers

## TASK 4 - Build a pipeline in Agno --> get keys from Tibo

## TASK 5 - Start writing my paper

I will complete Chapter 1 this week (2026-01-09 - 2026-01-15)

* **Chapter 1 - Introduction**
    * Background
    * Problem Formulation
    * Motivation
    * Objectives
    * Contributions of the work
    * Scope and limitations
    * Thesis structure

Collecting some papers this week will set me up well to do Chapter 2 next week:

* **Chapter 2 - Related work**
    * Review of existing research
    * Comparison of approaches
    * identified gaps and positioning of this work
    * summary