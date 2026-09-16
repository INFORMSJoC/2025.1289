# Python Basics
import math
import time

# External Dependencies
from docplex.cp.model import start_of, start_eval, CpoModel, interval_var, alternative, end_before_start, \
    pulse, presence_of, step_at_start, minimize, CpoSegmentedFunction, CpoModelSolution

from docplex.cp.solver.cpo_callback import CpoCallback

# Internal Dependencies
import src.Constants
from src.Interfaces import PricingProblem
from src.Solution import Solution


class Mycallback(CpoCallback):
    """
    Callback that interrupts search according to certain stopping criteria.

    Attributes:
        pricing_problem (PricingProblem): Pricing problem.
        sol_count (int): Number of improving solutions found.
        starting_iteration (int): Iteration count of the master problem at creation of Callback.
        master_iteration (int): Current iteration count of the master problem.
        time_of_last_solution (float): Time stamp when the last improving solution was found.

    Methods:
        invoke(solver, event, cp_solution):
            Checks the progress and terminates the search if necessary.
    """

    def __init__(self, pricing_problem, master_iteration):
        """
        Initializes callback for given constraint program.

        Args:
            pricing_problem (PricingProblem): Pricing problem.
            master_iteration (int): Iteration count of the master problem.
        """
        super(Mycallback, self).__init__()
        self.pricing_problem = pricing_problem
        self.sol_count = 0
        self.starting_iteration = master_iteration.value
        self.master_iteration = master_iteration

    def invoke(self, solver, event, cp_solution):
        """
        Checks the progress and terminates the search if necessary.

        Args:
            solver (docplex.cp.solver.solver): CP solver.
            event (str): Reason (state of the search) explaining why callback was invoked.
            cp_solution (docplex.cp.solution): Solution of the docplex.cp.model.CPOModel.
        """
        if event == "Solution":
            if cp_solution.get_objective_value() < -src.Constants.EPSILON:
                self.sol_count += 1
                self.pricing_problem.add_solution_to_pool(cp_solution)
                self.time_of_last_solution = time.perf_counter()

        if event != "EndSearch" and event != "EndSolve":
            # Abort if an improving column has been found and this solve has run longer
            # than GAMMA_CG since it started.
            if self.sol_count >= 1 and cp_solution.get_info('SolveTime') > src.Constants.GAMMA_CG:
                solver.abort_search()
            # Abort if the master problem has moved DELTA_CG iterations ahead of when this
            # pricing problem started, since its dual values are now stale.
            if (self.master_iteration.value - self.starting_iteration) >= src.Constants.DELTA_CG:
                solver.abort_search()


class PricingProblemCP(PricingProblem):
    """
    Pricing problem for column generation formulated as constraint program.

    Attributes:
        instance (Instance): Instance object representing the MRCMPSP instance.
        solution (Solution): Currently best known solution of the constraint program.
        solution_pool (List of Solution): Pool of solutions.
        objective_value (float): Objective value for currently best known solution.
        objective_bound (float): Currently best known bound for objective value.
        runtime (float): Runtime from last solve call.
        status (int): Status of the solving process (0:unsolved, 1:suboptimal, 2:optimal, 3:infeasible)
        project (Project): Project object representing the project corresponding to the pricing problem.
        model (docplex.cp.model.CPOModel): CP Optimizer model.
        x (dict): Set of interval variables representing activities.
        modes (dict): Set of interval variables representing modes.
        objective_function (docplex.cp.expression.CpoFunctionCall): Current objective function of the model.
        params (dict): Keyword parameters for solving process.

    Methods:
        populate_model():
            Populates the optimization model with the MRCMPSP instance data.

        solve(**params):
            Solves the optimization model.

        compute_start_time_costs(duals_k_t, makespan_ub):
            Computes the start time dependent costs of the activities for given dual values.

        generate_resource_costs_expression(start_time_costs, makespan_ub):
            Generates the resource costs expression for given start time dependent costs of the activities.

        update_objective(duals_i, duals_k_t):
            Updates the objective function for given dual values.

        set_starting_solution(column=None):
            Define starting solution for warm start.

        add_solution_to_pool(cp_solution):
            Adds solution to solution pool.
    """

    def __init__(self, instance, project):
        """
        Initializes pricing problem (constraint program).

        Args:
            instance (Instance): Instance object representing the MRCMPSP instance.
            project (Project): Project object representing the project corresponding to the pricing problem.
        """
        super().__init__(instance=instance, project=project)
        self.model = CpoModel()
        self.x = None
        self.modes = None
        self.objective_function = None
        self.params = {"TimeLimit": 3600, "ColumnLimit": src.Constants.INFINITY}

    def populate_model(self):
        """
        Populates the optimization model with the MRCMPSP instance data.
        """
        # Decision variables
        self.x = {j: interval_var(name=f"activity.{j}")
                  for j, activity in enumerate(self.project.activities)}

        self.modes = {(j, m): interval_var(name=f"activity[{j},{m}]", optional=True, size=activity.duration[m])
                      for j, activity in enumerate(self.project.activities)
                      for m in activity.modes}

        # Constraints
        # Select one mode for each activity
        self.model.add(alternative(self.x[j], [self.modes[j, m] for m in activity.modes])
                       for j, activity in enumerate(self.project.activities))

        # Time windows
        self.model.add(start_of(self.x[j]) >= activity.earliest_start
                       for j, activity in enumerate(self.project.activities))
        self.model.add(start_of(self.x[j]) <= activity.latest_start
                       for j, activity in enumerate(self.project.activities))

        # Precedence constraints
        self.model.add(end_before_start(self.x[j], self.x[j_prime])
                       for j, activity in enumerate(self.project.activities)
                       for j_prime in activity.successors)

        # Resource constraints
        # Global renewable resources
        global_resource_usage = {}
        for k, resource_type in enumerate(self.instance.resource_types):
            if resource_type == 0:
                global_resource_usage[k] = sum(pulse(self.modes[j, m], activity.resource_req[m][k])
                                               for j, activity in enumerate(self.project.activities)
                                               for m in activity.modes
                                               if activity.resource_req[m][k] > 0)

        self.model.add(global_resource_usage[k] <= capacity
                       for k, capacity in enumerate(self.instance.resource_capacities)
                       if self.instance.resource_types[k] == 0)

        # Local renewable resources
        local_renewable_resource_usage = {}
        for k, resource_type in enumerate(self.project.resource_types):
            if resource_type == 1:
                local_renewable_resource_usage[k] = sum(pulse(self.modes[j, m], activity.resource_req[m][k])
                                                        for j, activity in enumerate(self.project.activities)
                                                        for m in activity.modes
                                                        if activity.resource_req[m][k] > 0)

        self.model.add(local_renewable_resource_usage[k] <= capacity
                       for k, capacity in enumerate(self.project.resource_capacities)
                       if self.project.resource_types[k] == 1)

        # Global nonrenewable resources
        local_nonrenewable_resource_usage_presence = {}
        local_nonrenewable_resource_usage_step = {}
        for k, resource_type in enumerate(self.project.resource_types):
            if resource_type == 2:
                local_nonrenewable_resource_usage_presence[k] = sum(
                    presence_of(self.modes[j, m]) * activity.resource_req[m][k]
                    for j, activity in enumerate(self.project.activities)
                    for m in activity.modes
                    if activity.resource_req[m][k] > 0)

                local_nonrenewable_resource_usage_step[k] = sum(
                    step_at_start(self.modes[j, m], activity.resource_req[m][k])
                    for j, activity in enumerate(self.project.activities)
                    for m in activity.modes
                    if activity.resource_req[m][k] > 0)

        self.model.add(local_nonrenewable_resource_usage_presence[k] <= capacity
                       for k, capacity in enumerate(self.project.resource_capacities)
                       if self.project.resource_types[k] == 2)

        self.model.add(local_nonrenewable_resource_usage_step[k] <= capacity
                       for k, capacity in enumerate(self.project.resource_capacities)
                       if self.project.resource_types[k] == 2)

        # Objective
        self.objective_function = minimize(start_of(self.x[self.project.activities[-1].index])
                                           - self.project.release_date - self.project.critical_path_duration)
        self.model.add(self.objective_function)

    def solve(self, event=None, makespan_objective=False, master_iteration=None, **params):
        """
        Solves the optimization model.

        Args:
            makespan_objective (bool, optional): Indicates if the current objective is a makespan minimization.
            master_iteration (multiprocessing.Value, optional): Shared iteration count of the master problem,
                used by the solver callback to decide when to abort the search.

        Keyword Args:
            TimeLimit (int): Integer specifying the time limit for the solving process measured in seconds.
            OutputFlag (bool): Boolean indicating if the log file should be printed to the console during solving.
            ColumnLimit (bool): Indicating after how many columns (negative reduced costs solutions) the function shall
            terminate.
        Note:
            If current objective is the minimization of the makespan the parameter "makespan_objective" must be set to
            True. Otherwise, all non-negative makespan solutions are cut-off.
        """

        # Set starting solution
        self.set_starting_solution()

        # Reset solving statistics and solutions
        self.status = 0
        self.solution_pool.clear()
        self.solution_ids = {}
        self.solution = None
        self.objective_value = src.Constants.INFINITY
        self.objective_bound = -src.Constants.INFINITY

        # Update solving parameters
        for key, val in params.items():
            self.params[key] = val

        # Solve Model and collect solving statistics
        start_time = time.perf_counter()
        status = None
        callback = Mycallback(pricing_problem=self, master_iteration=master_iteration)
        self.model.add_solver_callback(callback)
        sol = self.model.solve(TimeLimit=self.params["TimeLimit"], Workers=1, LogVerbosity="Quiet",
                               RandomSeed=src.Constants.SEED)
        status = sol.get_solve_status()
        self.objective_bound = sol.get_objective_bound()
        if status == "Optimal":
            self.status = 2
        elif status == "Infeasible":
            self.status = 3
        self.runtime = time.perf_counter() - start_time

    def compute_start_time_costs(self, duals_k_t, makespan_ub):
        """
        Computes the start time dependent costs of the activities for given dual values.

        Args:
            duals_k_t (numpy.array): Array of dual values corresponding to global resource constraints.
            makespan_ub (int): Upper bound on the makespan.
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
                                if s <= self.instance.planning_horizon[-1]:
                                    start_time_costs[j, m, t] += (duals_k_t[k - offset][s] * activity.resource_req[m][k])
                                else:
                                    start_time_costs[j, m, t] = -src.Constants.INFINITY
                        else:
                            offset += 1
        return start_time_costs

    def generate_resource_costs_expression(self, start_time_costs, makespan_ub):
        """
        Generates the resource costs expression for given start time dependent costs of the activities.

        Args:
            start_time_costs (dict): Dictionary of start time costs.
            makespan_ub (int): Upper bound on the makespan.
        """
        step_function = {}
        for j, activity in enumerate(self.project.activities):
            for m in activity.modes:
                step = CpoSegmentedFunction()
                start = activity.earliest_start
                for t in range(activity.earliest_start + 1, activity.latest_start + 1):
                    if abs(start_time_costs[j, m, t] - start_time_costs[j, m, t - 1]) > src.Constants.FEASIBILITY_TOLERANCE:# or True:
                        step.add_value(start, t, -start_time_costs[j, m, t - 1])
                        #print(f"({t-1}, {-start_time_costs[j, m, t - 1]}, 0)", end=" ")
                        start = t
                        if t == activity.latest_start:
                            step.add_value(start, t + 1, -start_time_costs[j, m, t])
                            start = t
                    elif t == activity.latest_start and start_time_costs[j, m, t] != 0:
                        step.add_value(start, t + 1, -start_time_costs[j, m, t])
                        start = t
                step_function[j, m] = step

        resource_costs = sum([start_eval(self.modes[j, m], step_function[j, m], absentValue=0)
                              for j, activity in enumerate(self.project.activities)
                              for m in activity.modes
                              if len(step_function[j, m].get_segment_list()) > 0])

        return resource_costs

    def update_objective(self, duals_i, duals_k_t):
        """
        Updates the objective function for given dual values.

        Args:
            duals_i (numpy.array): Array of dual values corresponding to convexity constraints.
            duals_k_t (numpy.array): Array of dual values corresponding to global resource constraints.
        """
        self.model = CpoModel()
        self.populate_model()
        makespan_ub = duals_i[self.project.index] + self.project.release_date + self.project.critical_path_duration
        makespan_ub = math.ceil(makespan_ub + src.Constants.INTEGRALITY_TOLERANCE)
        start_time_costs = self.compute_start_time_costs(duals_k_t=duals_k_t, makespan_ub=makespan_ub)
        resource_costs = self.generate_resource_costs_expression(start_time_costs=start_time_costs,
                                                                 makespan_ub=makespan_ub)
        original_costs = start_of(self.x[self.project.activities[-1].index]) - self.project.release_date \
                         - self.project.critical_path_duration

        new_objective = minimize(original_costs + resource_costs - duals_i[self.project.index])
        self.model.replace_expression(self.objective_function, new_objective)
        self.objective_function = new_objective

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

        starting_solution = CpoModelSolution()
        for j, activity in enumerate(self.project.activities):
            start_time = start_times[self.project.index, j]
            mode = modes[self.project.index, j]
            end_time = start_time + activity.duration[mode]
            starting_solution.add_interval_var_solution(self.x[j], start=start_time, end=end_time)
            starting_solution.add_interval_var_solution(self.modes[j, mode], start=start_time, end=end_time,
                                                        presence=True)
        self.model.set_starting_point(starting_solution)

    def add_solution_to_pool(self, cp_solution):
        """
        Adds solution to solution pool.

        Args:
            cp_solution (docplex.cp.solution): Solution of the docplex.cp.model.CPOModel.
        """
        self.status = 1
        start_times = {}
        modes = {}
        for j, activity in enumerate(self.project.activities):
            for m in activity.modes:
                if cp_solution.get_var_solution(self.modes[j, m]).is_present():
                    start_times[self.project.index, j] = cp_solution.get_var_solution(self.x[j]).start
                    modes[self.project.index, j] = m

        sol = Solution(instance=self.instance, start_times=start_times, modes=modes,
                       objective_value=cp_solution.get_objective_value(), projects=[self.project])
        self.solution_pool.append(sol)

        if cp_solution.get_objective_value() <= self.objective_value:
            self.solution = sol
            self.objective_value = sol.objective_value

