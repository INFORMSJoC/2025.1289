# Source Code

This directory contains the implementation used by `scripts/main.py`:

- `Instance.py`, `Project.py`, `Activity.py`: the MRCMPSP data model (instances, projects, activities, modes, and resources).
- `Interfaces.py`: abstract base classes shared by the optimization models (`OptimizationModel`, `PricingProblem`).
- `IntegerProgram.py`: the monolithic time-indexed IP formulation.
- `ConstraintProgram.py`: the monolithic CP formulation.
- `MasterProblem.py`: the restricted master problem of the Dantzig-Wolfe decomposition.
- `PricingProblemIP.py`, `PricingProblemCP.py`, `CPSubproblem.py`: the IP and CP formulations of the per-project pricing problem.
- `Column.py`, `Solution.py`: the column-pool and solution representations shared across the master and pricing problems.
- `Hybrid_Solver.py`: the hybrid CP-based Dantzig-Wolfe decomposition (CP-DWD) framework, implementing CP-OBBT (presolve), CP-LNS (primal heuristic), and CP-IP-CG (dual bound computation), including their parallelization.
- `Constants.py`: shared numerical tolerances and the CP-OBBT/CP-LNS/CP-IP-CG hyperparameters.
