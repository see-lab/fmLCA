# Design Document: Integrating Modelica and LCA FMUs in Python

## Progress Tracker

| Step                                                                 | Status |
|----------------------------------------------------------------------|--------|
| Import a Modelica FMU into Python                                    | [x]    |
| Output power from Modelica FMU                                       | [x]    |
| Connect power output to a second (basic) FMU                         | [ ]    |
| Add feedback from second FMU to Modelica FMU                         | [ ]    |
| Generate basic LCA (e.g., block of steel or water bottle)            | [ ]    |
| Compile LCA into an FMU                                              | [ ]    |
| Make LCA power input externally controllable                         | [ ]    |
| Add output feedback from LCA FMU                                     | [ ]    |
| Connect Modelica and LCA FMUs with feedback                          | [ ]    |
| Implement Python simulation loop for co-simulation                   | [ ]    |
| Investigate LCA precompilation/vectorization                         | [ ]    |
| Define feedback in terms of optimization targets (e.g., turbine count) | [ ]    |


## Objective

Build a minimal framework to integrate FMUs from both Modelica-based dynamic models and static LCA models within a Python environment, enabling feedback between them.

---

## Part 1: Modelica FMU in Python

### Goal
Set up a simple Modelica FMU in Python and interact with it using another FMU via feedback.

### Steps

1. **Import a Modelica FMU into Python**
   - Use `fmpy` or similar library.
   - Run and simulate with minimal setup.

2. **Output Power from Modelica FMU**
   - Identify a power-related output.
   - Connect it as input to a second (simple) FMU.

3. **Introduce Feedback**
   - Create a minimal second FMU (e.g., simple gain or control FMU).
   - Feed its output back into the Modelica FMU input.

### Ingredients
- Modelica FMU  
- FMU solver (e.g., CVODE via `fmpy`)  
- Python-based simulation loop  
- Basic feedback logic  

---

## Part 2: LCA FMU Construction

### Goal
Wrap a basic LCA model as an FMU and integrate it into the same Python-based simulation loop.

### Steps

1. **Generate LCA Model**
   - Option A: Reuse existing LCA model (e.g., water bottle).
   - Option B: Create minimal LCA (e.g., block of steel with power input).

2. **Compile LCA to FMU**
   - Use LCA-to-FMU tooling or generate a wrapper manually (e.g., using `pyfmi` or `pythonfmu`).

3. **Make Power Input Configurable**
   - Define `power_input` as an external FMU input.

4. **Add Feedback**
   - Expose an output variable (e.g., carbon impact) from the LCA FMU.
   - Feed this into the control logic or Modelica FMU.

---

## Solver Considerations

- LCA is effectively a static, steady-state system.
- The “solver” is simply evaluating the inventory.
- For stochastic/MultiLCA:
  - Pre-run samples and cache results.
  - Wrap sampling as part of the FMU logic if needed.

### Open Questions

- Can the LCA be precompiled or vectorized for efficiency?
- How to cache or optimize LCA computation across iterations?

---

## Integration and Simulation Loop

### Goal
Simulate a co-simulation of the two FMUs with simple feedback.

### Tasks

- Set up Python loop to step both FMUs in sync.
- Pass `power_output` from Modelica to LCA.
- Pass `impact_output` from LCA to Modelica (or intermediary).
- Synchronize time steps and solver calls.

---

## Potential Extensions

1. **Precompilation of LCA FMU**
   - Vectorized static evaluation.
   - Avoid full recomputation per iteration.

2. **Optimization-Driven Feedback**
   - Use FMU outputs in optimization loop.
   - Example: “How many turbines minimize total impact?”

---

## Summary

This system provides a minimal hybrid simulation of dynamic (Modelica) and static (LCA) systems, with extensible feedback. Initial focus is correctness and simplicity, with optimization and performance refinements as follow-up steps.
