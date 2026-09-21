# Scripts

These scripts reproduce the computational experiments in the paper. Run them from the repository root so relative paths resolve correctly.

```bash
python scripts/main.py
python scripts/main_no_presolve.py
python scripts/main_no_primal_heuristic.py
python scripts/monolithic_baseline.py
```

`main.py` iterates over all instances in `../data/MISTA`, loads each as an `Instance`, and solves it with the full CP-DWD hybrid solver (`src/Hybrid_Solver.py`).

`main_no_presolve.py` runs the same CP-DWD procedure with the CP-OBBT presolve phase disabled (`DisableOBBT=True`).

`main_no_primal_heuristic.py` runs the same CP-DWD procedure with the CP-LNS primal heuristic phase disabled (`DisableLNS=True`).

`monolithic_baseline.py` iterates over the same instances and solves each with the monolithic CP (`src/ConstraintProgram.py`) and monolithic IP (`src/IntegerProgram.py`) formulations, reproducing the monolithic-model baselines reported in the paper.

Time limits and CP-OBBT/CP-LNS/CP-IP-CG hyperparameters are configured in `src/Constants.py`. The remaining two algorithmic configurations considered in the paper, **CP-LNS+IP-CG** and **CP+CP-IP-CG**, don't require separate scripts -- they're reached by adjusting these hyperparameters instead:

- **CP-LNS+IP-CG**: set `ALPHA_CG` to the full time budget (3600s in our experiments).
- **CP+CP-IP-CG**: set `ALPHA_LNS`, `GAMMA_LNS`, and `BETA_LNS` all equal to `TIME_LIMIT_LNS`.
