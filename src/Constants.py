import math

INFINITY = math.inf
FEASIBILITY_TOLERANCE = 0.00001
OPTIMALITY_TOLERANCE = 0.001
EPSILON = 0.0001
INTEGRALITY_TOLERANCE = 0.0001
SEED = 0

# Hyperparameter CP-OBBT
ALPHA_OBBT = 60  # time limit (seconds) for each CP-OBBT solve

# (Hyper)Parameters CP-LNS
TIME_LIMIT_LNS = 600  # total time budget (seconds) for the CP-LNS phase
ALPHA_LNS = 600  # time limit (seconds) for the LNS starting-heuristic solve
BETA_LNS = 60  # max seconds without an improving solution before LNS starting-heuristic aborts
GAMMA_LNS = 60  # time limit (seconds) per LNS neighborhood solve

# Hyperparameter CP-IP-CG
ALPHA_CG = 700  # CP-CG stops once fewer than this many seconds remain in the time budget
DELTA_CG = 10  # max master-problem iterations a pricing problem lags behind before it is aborted and restarted
GAMMA_CG = 0.1  # per CP-pricing-problem time limit (seconds) once at least one column has been found
ZETA_CG = 300  # time limit (seconds) for an IP-pricing-problem solve