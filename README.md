[![INFORMS Journal on Computing Logo](https://INFORMSJoC.github.io/logos/INFORMS_Journal_on_Computing_Header.jpg)](https://pubsonline.informs.org/journal/ijoc)

# Combining CP and IP for Dantzig-Wolfe Decomposition: An Application to Multi-Project Scheduling

This archive is distributed in association with the [INFORMS Journal on Computing](https://pubsonline.informs.org/journal/ijoc) under the [MIT License](LICENSE).

The software and data in this repository are a snapshot of the code and data that were used in the research paper Combining CP and IP for Dantzig-Wolfe Decomposition: An Application to Multi-Project Scheduling by M. Kolter,  J. C. Beck, M. Grunow, R. Kolisch.

## Cite

To cite the contents of this repository, please cite both the paper and this repository using their respective DOIs.

Paper DOI:

```text
https://doi.org/xxx.xxxx/ijoc.xxxx.xxxx
```

Code repository DOI:

```text
https://doi.org/10.1287/ijoc.2025.1289.cd
```

BibTeX for this repository snapshot:

```bibtex
@misc{Kolter2026CPDWD,
  author = {Kolter, Maximilian and Beck, J. Christopher and Grunow, Martin and Kolisch, Rainer},
  publisher = {INFORMS Journal on Computing},
  title = {Combining CP and IP for Dantzig-Wolfe Decomposition: An Application to Multi-Project Scheduling},
  year = {2026},
  doi = {10.1287/ijoc.2025.1289.cd},
  url = {https://github.com/INFORMSJoC/2025.1289},
  note = {Available for download at https://github.com/INFORMSJoC/xxxx.xxxx},
}
```

## Description

This repository contains the Python implementation of a hybrid CP-based Dantzig-Wolfe decomposition (CP-DWD) framework for the multi-mode resource-constrained multi-project scheduling problem (MRCMPSP) with global and local resources. The framework combines constraint programming (CP), integer programming (IP), and metaheuristic techniques to compute both primal and dual bounds along the entire solution chain: presolve, primal heuristic, and dual bound computation. For more details please refer to the main paper.

## Repository Structure

```
.
├── README.md
├── AUTHORS
├── LICENSE
├── requirements.txt
├── Data/
│   ├── README.md
│   ├── MISTA/                            # 30 benchmark instances from the MISTA 2013 challenge
│   └── MISTA_AB/                         # 60 additional instances with varied global resource capacities
├── scripts/
│   ├── README.md
│   ├── main.py                           # Entry point that solves instances via CP-DWD
│   ├── main_no_presolve.py               # CP-DWD with the CP-OBBT presolve phase disabled
│   ├── main_no_primal_heuristic.py       # CP-DWD with the CP-LNS primal heuristic phase disabled
│   └── monolithic_baseline.py            # Entry point that solves instances via the monolithic CP and IP baselines
└── src/
    ├── README.md
    ├── Instance.py, Project.py, Activity.py
    │                                     # MRCMPSP data model
    ├── Interfaces.py                     # Abstract base classes for optimization models
    ├── IntegerProgram.py                 # Monolithic IP formulation
    ├── ConstraintProgram.py              # Monolithic CP formulation
    ├── MasterProblem.py                  # Restricted master problem of the Dantzig-Wolfe decomposition
    ├── PricingProblemIP.py, PricingProblemCP.py, CPSubproblem.py
    │                                     # IP and CP pricing-problem formulations
    ├── Column.py, Solution.py            # Column pool and solution representations
    └── Hybrid_Solver.py                  # CP-OBBT, CP-LNS, and CP-IP-CG algorithmic components

```

The main directories are:

- `src/`: the MRCMPSP data model, the monolithic CP and IP formulations, the Dantzig-Wolfe master and pricing problems, and the CP-DWD hybrid solver (CP-OBBT, CP-LNS, CP-IP-CG).
- `scripts/`: the experiment drivers that solve instances via CP-DWD (`main.py`), via CP-DWD with the presolve or primal heuristic phase disabled for the ablation experiments (`main_no_presolve.py`, `main_no_primal_heuristic.py`), and via the monolithic CP and IP baselines (`monolithic_baseline.py`).
- `data/`: local copies of the 30 MISTA 2013 challenge instances (`MISTA/`) and the 60 additional instances with varied global resource capacities (`MISTA_AB/`).

## Dependencies

The code requires Python 3.10+ and package dependencies are listed in `requirements.txt`. The optimization models require a working Gurobi installation and license (for the IP components) and a working IBM CP Optimizer installation and license, accessed via `docplex` (for the CP components).

Install dependencies with:

```bash
python -m pip install -r requirements.txt
```

## Replicating Results

Run commands from the repository root.

```bash
python scripts/main.py
python scripts/main_no_presolve.py
python scripts/main_no_primal_heuristic.py
python scripts/monolithic_baseline.py
```

`scripts/main.py` iterates over all instances in `data/MISTA` and solves each with the full CP-DWD hybrid solver. `scripts/main_no_presolve.py` and `scripts/main_no_primal_heuristic.py` run the same CP-DWD procedure over the same instances with, respectively, the CP-OBBT presolve phase (`DisableOBBT=True`) and the CP-LNS primal heuristic phase (`DisableLNS=True`) disabled, reproducing the corresponding ablation experiments reported in the paper. `scripts/monolithic_baseline.py` iterates over the same instances and solves each with the monolithic CP and IP formulations, reproducing the monolithic-model comparisons reported in the paper. Solver time limits and CP-OBBT/CP-LNS/CP-IP-CG hyperparameters (`ALPHA_OBBT`, `TIME_LIMIT_LNS`, `ALPHA_LNS`, `BETA_LNS`, `GAMMA_LNS`, `ALPHA_CG`, `GAMMA_CG`, `ZETA_CG`, `Delta_CG`) are configured in `src/Constants.py`.

For the remaining ablation configurations considered in the paper, see `scripts/README.md` for the hyperparameter adjustments needed to reproduce each one.

Full experiment runs on the MISTA benchmark set are computationally intensive (a time limit of 3,600 seconds per instance was used in the paper). To verify the installation with a small run, reduce `time_limit` in `scripts/main.py` or `scripts/monolithic_baseline.py` and/or point `dir_path` at a subset of instances.

## Data

The MRCMPSP instances used in the computational experiments are included under `data/`. See `data/README.md` for source citations and license information.

## Results

Please view the main paper and Supplemental Material.

## Support

For questions about this repository, please contact the authors listed in `AUTHORS`.
