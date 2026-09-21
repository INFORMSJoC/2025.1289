# Python Basics
import time

# External Dependencies
import gurobipy as gp
from gurobipy import GRB

# Internal Dependencies
import src.Constants
from src.Instance import Instance
from src.Interfaces import PricingProblem
from src.Solution import Solution


class PricingProblemIP(PricingProblem):
    """
    Pricing problem for column generation formulated as integer program.

    Attributes:
        instance (Instance): Instance object representing the MRCMPSP instance.
        solution (Solution): Currently best known solution of the constraint program.
        solution_pool (List of Solution): Pool of solutions.
        objective_value (float): Objective value for currently best known solution.
        objective_bound (float): Currently best known bound for objective value.
        runtime (float): Runtime from last solve call.
        status (int): Status of the solving process (0:unsolved, 1:suboptimal, 2:optimal, 3:infeasible)
        project (Project): Project object representing the project corresponding to the pricing problem.
        model (gurobipy.Model): Gurobi model.
        x (dict): Set of interval variables representing activities.
        global_resource_cons (dict): Set of global resource constraints.
        branching_cons (list): List of branching constraints added to the model.
        params (dict): Keyword parameters for solving process.

    Methods:
        populate_model():
            Populates the optimization model with the MRCMPSP instance data.

        solve(**params):
            Solves the optimization model.

        compute_start_time_costs(duals_k_t):
            Computes the start time dependent costs of the activities for given dual values.

        generate_resource_costs_expression(start_time_costs):
            Generates the resource costs expression for given start time dependent costs of the activities.

        update_objective(duals_i, duals_k_t):
            Updates the objective function for given dual values.

        add_solution_to_pool():
            Adds solution to solution pool.

        set_starting_solution(column=None):
            Define starting solution for warm start.
    """

    def __init__(self, instance, project):
        """
        Initializes pricing problem (integer program).

        Args:
            instance (Instance): Instance object representing the MRCMPSP instance.
            project (Project): Project object representing the project corresponding to the pricing problem.
        """
        super().__init__(instance=instance, project=project)
        self.model = gp.Model()
        self.x = None
        self.global_resource_cons = {}
        self.branching_cons = []
        self.params = {"TimeLimit": 3600, "ColumnLimit": src.Constants.INFINITY, "OutputFlag": False, "deadline": None}

    def populate_model(self):
        """
        Populates the optimization model with the MRCMPSP instance data.
        """
        # Decision variables
        self.x = self.model.addVars([(j, m, t)
                                     for j, activity in enumerate(self.project.activities)
                                     for m in activity.modes
                                     for t in range(activity.earliest_start, activity.latest_start+1)],
                                    vtype=GRB.BINARY, name="x")
        # Constraints
        # Start every activity once in exactly one mode
        for j, activity in enumerate(self.project.activities):
            self.model.addConstr((gp.quicksum(self.x[j, m, t]
                                              for m in activity.modes
                                              for t in range(activity.earliest_start, activity.latest_start + 1))
                                  == 1),
                                 name=f"start_once[{j}]")

        # Precedence constraints
        for j, activity in enumerate(self.project.activities):
            for j_prime in activity.successors:
                self.model.addConstr((gp.quicksum((t + activity.duration[m])*self.x[j, m, t]
                                                  for m in activity.modes
                                                  for t in range(activity.earliest_start, activity.latest_start+1))
                                      <= gp.quicksum(t*self.x[j_prime, m, t]
                                                     for m in self.project.activities[j_prime].modes
                                                     for t in range(self.project.activities[j_prime].earliest_start,
                                                                    self.project.activities[j_prime].latest_start+1))),
                                     name=f"precedence[{j},{j_prime}]")

        # Global resources constraints
        for k, capacity in enumerate(self.instance.resource_capacities):
            if self.instance.resource_types[k] == 0:
                for t in self.instance.planning_horizon:
                    self.global_resource_cons[k, t] =  self.model.addConstr(
                        (gp.quicksum(activity.resource_req[m][k] * self.x[j, m, s]
                                     for j, activity in enumerate(self.project.activities)
                                     for m in activity.modes
                                     for s in
                                     range(max(activity.earliest_start, t - activity.duration[m]+1),
                                           min(activity.latest_start, t)+1))
                         <= capacity),
                        name=f"global_resources[{k},{t}]")

        # Local renewable resources constraints
        for k, capacity in enumerate(self.project.resource_capacities):
            if self.project.resource_types[k] == 1:
                for t in range(self.project.release_date, self.project.activities[-1].latest_start + 1):
                    self.model.addConstr((gp.quicksum(activity.resource_req[m][k] * self.x[j, m, s]
                                                      for j, activity in enumerate(self.project.activities)
                                                      for m in activity.modes
                                                      for s in range(max(activity.earliest_start,
                                                                         t - activity.duration[m]+1),
                                                                     min(activity.latest_start, t)+1))
                                          <= capacity),
                                         name=f"local_renewable_resources[{k},{t}]")

        # Local nonrenewable resources constraints
        for k, capacity in enumerate(self.project.resource_capacities):
            if self.project.resource_types[k] == 2:
                #for t in range(self.project.release_date, self.project.activities[-1].latest_start + 1):
                self.model.addConstr((gp.quicksum(activity.resource_req[m][k] * self.x[j, m, t]
                                                  for j, activity in enumerate(self.project.activities)
                                                  for m in activity.modes
                                                  for t in range(activity.earliest_start,
                                                                 activity.latest_start + 1))
                                      <= self.project.resource_capacities[k]),
                                     name=f"local_nonrenewable_resources[{k}]")

    def solve(self, event=None, counter=None, bounding=None, **params):
        """
        Solves the optimization model.

        Args:
            event (multiprocessing.Event, optional): Event signaling that the master problem has converged;
                checked by the solver callback to decide when to terminate.
            counter (multiprocessing.Value, optional): Shared counter of pricing problems that finished
                their LP relaxation.
            bounding (str, optional): Indicates the bounding mode ("LP" or "IP"); if not "LP", solutions found
                in the solution pool are added via add_solution_to_pool().

        Keyword Args:
            TimeLimit (int): Integer specifying the time limit for the solving process measured in seconds.
            OutputFlag (bool): Boolean indicating if the log file should be printed to the console during solving.
            ColumnLimit (bool): Indicating after how many columns (negative reduced costs solutions) the function shall
            terminate.
        """
        # Update solving parameters
        for key, val in params.items():
            self.params[key] = val
        if self.params["OutputFlag"]:
            self.model.setParam("OutputFlag", 1)
        else:
            self.model.setParam("OutputFlag", 0)
        self.model.setParam("TimeLimit", self.params["TimeLimit"])
        self.model.setParam("Threads", 1)
        self.model.setParam("Seed", src.Constants.SEED)
        # These model._* fields exist purely to pass state into the solution_counter
        # callback below, which Gurobi invokes with only (model, where) as arguments.
        self.model._sol_count = 0
        self.model._ColumnLimit = self.params["ColumnLimit"]
        self.model._start_time = time.perf_counter()
        self.model._deadline = self.params["deadline"]
        self.model._master_event = event
        self.model._lp_phase_logged = True
        self.model._shared_counter = counter
        self.model._project_count = len(self.instance.projects)

        # Reset solving statistics and solutions
        self.solution_pool.clear()
        self.solution = None
        self.objective_value = src.Constants.INFINITY
        self.objective_bound = -src.Constants.INFINITY

        # Solve Model and collect solving statistics
        start_time = time.perf_counter()
        self.model.optimize(solution_counter)

        # Only "LP" is treated specially here; any other value (including "IP", None, or a typo)
        # takes this branch.
        if bounding != "LP":
            self.objective_bound = self.model.ObjBound
            if self.model.SolCount > 0:
                for i in range(self.model.SolCount):
                    self.model.setParam(GRB.Param.SolutionNumber, i)
                    if self.model.PoolObjVal < -src.Constants.EPSILON:
                        self.status = 1
                        self.add_solution_to_pool()
        if self.model.Status == 3:
            self.status = 3
        else:
            self.objective_bound = self.model.ObjBound
            if abs(self.objective_bound - self.objective_value) < src.Constants.OPTIMALITY_TOLERANCE:
                self.status = 2
        self.runtime = time.perf_counter() - start_time

    def compute_start_time_costs(self, duals_k_t):
        """
        Computes the start time dependent costs of the activities for given dual values.

        Args:
            duals_k_t (numpy.array): Array of dual values corresponding to global resource constraints.
        """
        # duals_k_t is only indexed by global resources, so offset tracks how many
        # non-global resource types have been skipped so far, to realign k (which
        # ranges over all resource types) with duals_k_t's global-only indexing.
        start_time_costs = {}
        for j, activity in enumerate(self.project.activities):
            for m in activity.modes:
                for t in range(activity.earliest_start, activity.latest_start + 1):
                    start_time_costs[j, m, t] = 0
                    offset = 0
                    for k, resource_type in enumerate(self.project.resource_types):
                        if resource_type == 0:
                            for s in range(t, t + activity.duration[m]):
                                if s <= self.project.activities[-1].latest_start:
                                    start_time_costs[j, m, t] += duals_k_t[k - offset][s] * activity.resource_req[m][k]
                        else:
                            offset += 1
        return start_time_costs

    def generate_resource_costs_expression(self, start_time_costs):
        """
        Generates the resource costs expression for given start time dependent costs of the activities.

        Args:
            start_time_costs (dict): Dictionary of start time costs.
        """
        resource_costs = gp.quicksum(start_time_costs[j, m, t] * self.x[j, m, t]
                                     for j, activity in enumerate(self.project.activities)
                                     for m in activity.modes
                                     for t in range(activity.earliest_start,
                                                    activity.latest_start + 1))
        return resource_costs

    def update_objective(self, duals_i, duals_k_t):
        """
        Updates the objective function for given dual values.

        Args:
            duals_i (numpy.array): Array of dual values corresponding to convexity constraints.
            duals_k_t (numpy.array): Array of dual values corresponding to global resource constraints.
        """
        sink_activity = self.project.activities[-1]
        weighted_completion_time = gp.quicksum(t * self.x[sink_activity.index, m, t]
                                               for m in sink_activity.modes
                                               for t in range(sink_activity.earliest_start,
                                                              sink_activity.latest_start + 1))
        original_cost = weighted_completion_time - self.project.release_date - self.project.critical_path_duration

        start_time_costs = self.compute_start_time_costs(duals_k_t=duals_k_t)
        resource_costs = self.generate_resource_costs_expression(start_time_costs=start_time_costs)
        self.model.setObjective((original_cost - resource_costs - duals_i[self.project.index]), sense=GRB.MINIMIZE)

    def add_solution_to_pool(self):
        """
        Adds solution to solution pool.
        """
        start_times = {}
        modes = {}
        values = self.model.getAttr("Xn", self.x)
        for j, activity in enumerate(self.project.activities):
            value_added = False
            for m in activity.modes:
                if value_added:
                    break
                for t in range(activity.earliest_start, activity.latest_start + 1):
                    if values[j, m, t] > src.Constants.INTEGRALITY_TOLERANCE:
                        start_times[self.project.index, j] = t
                        modes[self.project.index, j] = m
                        value_added = True
                        break

        sol = Solution(instance=self.instance, start_times=start_times, modes=modes,
                       objective_value=self.model.PoolObjVal, projects=[self.project])
        self.solution_pool.append(sol)

        if self.model.PoolObjVal < self.objective_value:
            self.solution = sol
            self.objective_value = sol.objective_value

    def set_starting_solution(self, column=None):
        """
        Define starting solution for warm start.

        Args:
            column (Column, optional): Column from which starting solution is retrieved.

        Note:
            If no column is given the best known solution from the last solve is used as starting solution.
        """
        start_times = None
        modes = None
        if column is not None:
            start_times = column.start_times
            modes = column.modes
        elif self.solution is not None:

            start_times = self.solution.start_times
            modes = self.solution.modes
        else:
            return 0

        # Unlike PricingProblemCP (which rebuilds a fresh CpoModel on every update_objective
        # call), this class reuses the same Gurobi model across iterations. The else branch
        # below is therefore required, not redundant: it clears .Start hints left over from
        # a previous iteration's different (mode, time) assignment.
        for j, activity in enumerate(self.project.activities):
            start_time = start_times[self.project.index, j]
            mode = modes[self.project.index, j]
            for m in activity.modes:
                for t in range(activity.earliest_start, activity.latest_start+1):
                    if m == mode and t == start_time:
                        self.x[j, m, t].Start = 1.0
                    else:
                        self.x[j, m, t].Start = 0.0


def solution_counter(model, where):
    """
    Callback to terminate search if a certain number of solutions is found.

    Args:
        model (gurobipy.model): Gurobi model being solved.
        where (int): Indicating why the callback was triggered.
    """
    if where == GRB.Callback.MIPSOL:
        if model.cbGet(GRB.Callback.MIPSOL_OBJ) < -src.Constants.EPSILON:
            model._sol_count += 1
            model._master_event.set()

    elif where == GRB.Callback.MIP or where == GRB.Callback.MIPNODE:
        if model._lp_phase_logged == True:
            print(f"pricing problem {model._shared_counter} solved LP")
            model._shared_counter.value += 1
            model._lp_phase_logged = False
            print(f"pricing problem {model._shared_counter.value}")

        converged = model._shared_counter.value == model._project_count and model._master_event.is_set() \
            and time.perf_counter() - model._start_time > src.Constants.ZETA_CG
        past_deadline = model._deadline is not None and time.perf_counter() >= model._deadline
        if converged or past_deadline:
            print(f"terminate model because of time constraint {time.perf_counter() - model._start_time}")
            model.terminate()
