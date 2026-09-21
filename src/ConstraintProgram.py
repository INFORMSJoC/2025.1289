# Python Basics
import os
import time

# Internal Dependencies
import src.Constants
from src.Interfaces import OptimizationModel
from src.Solution import Solution

# External Dependencies
from docplex.cp.model import CpoModel, CpoCallback, interval_var, alternative, start_of, end_before_start, \
    pulse, presence_of, minimize, end_of


class ProgressCallback(CpoCallback):
    """
    Callback that interrupts search if no improving solution was found within a given time limit.

    Attributes:
        cp (ConstraintProgram): Constraint program.
        time_of_last_solution (float): Time stamps when last solution was found.
        sol_count (int): Number of solutions found.
        objective_value (float): Current objective function value.

    Methods:
        invoke(solver, event, cp_solution):
            Checks the progress and terminates the search if necessary.
    """

    def __init__(self, cp):
        """
        Initializes callback for given constraint program.

        Args:
            cp (ConstraintProgram): Constraint program.
        """
        super(ProgressCallback, self).__init__()
        self.cp = cp
        self.time_of_last_solution = None
        self.sol_count = 0
        self.objective_value = src.Constants.INFINITY

    def invoke(self, solver, event, cp_solution):
        """
        Checks the progress and terminates the search if necessary.

        Args:
            solver (docplex.cp.solver.solver): CP solver.
            event (str): Reason (state of the search) explaining why callback was invoked.
            cp_solution (docplex.cp.solution): Solution of the docplex.cp.model.CPOModel.
        """
        if event == "Solution":
            self.objective_value = cp_solution.get_objective_value()
            self.sol_count += 1
            self.cp.add_solution_to_pool(cp_solution)
            self.time_of_last_solution = time.perf_counter()

        if event != "EndSearch" and event != "EndSolve":
            if self.sol_count > 0:
                # time_of_last_solution is guaranteed to be set here, since sol_count > 0
                # implies the "Solution" branch above has run at least once.
                if time.perf_counter() - self.time_of_last_solution > src.Constants.BETA_LNS:
                    solver.abort_search()


class ConstraintProgram(OptimizationModel):
    """
    Constraint program for an MRCMPSP instance.

    Attributes:
        instance (Instance): Instance object representing the MRCMPSP instance.
        solution (Solution): Currently best known solution of the constraint program.
        solution_pool (List of Solution): Pool of solutions.
        objective_value (float): Objective value for currently best known solution.
        objective_bound (float): Currently best known bound for objective value.
        runtime (float): Runtime from last solve call.
        status (int): Status of the solving process (0:unsolved, 1:suboptimal, 2:optimal, 3:infeasible)
        model (docplex.cp.model.CPOModel): CP Optimizer model.
        x (dict): Set of interval variables representing activities.
        modes (dict): Set of interval variables representing modes.
        params (dict): Keyword parameters for solving process.

    Methods:
        populate_model():
            Populates the optimization model with the MRCMPSP instance data.

        solve(**params):
            Solves the optimization model.

        add_upper_bound_constraint(upper_bound):
            Adds a constraint on the upper bound of the objective function.

        add_solution_to_pool(cp_solution):
            Adds solution to solution pool.
    """

    def __init__(self, instance=None):
        """
        Initializes constraint program.

        Args:
            instance (Instance, optional): Instance object representing the MRCMPSP instance.
        """
        super().__init__(instance=instance)
        self.model = CpoModel()
        self.x = None
        self.modes = None
        self.params = {"TimeLimit": 3600, "ColumnLimit": src.Constants.INFINITY, "OutputFlag": True,
                       "Worker": os.cpu_count()}

    def populate_model(self):
        """
        Populates the optimization model with the MRCMPSP instance data.
        """
        # Decision variables
        self.x = {(i, j): interval_var(name=f"activity[{i},{j}]")
                  for i, project in enumerate(self.instance.projects)
                  for j, activity in enumerate(project.activities)}

        self.modes = {(i, j, m): interval_var(name=f"activity[{i},{j},{m}]", optional=True, size=activity.duration[m])
                      for i, project in enumerate(self.instance.projects)
                      for j, activity in enumerate(project.activities)
                      for m in activity.modes}

        # Constraints
        # Select one mode for each activity
        self.model.add(alternative(self.x[i, j], [self.modes[i, j, m] for m in activity.modes])
                       for i, project in enumerate(self.instance.projects)
                       for j, activity in enumerate(project.activities))

        # Time windows
        self.model.add(start_of(self.x[i, j]) >= activity.earliest_start
                       for i, project in enumerate(self.instance.projects)
                       for j, activity in enumerate(project.activities))
        self.model.add(start_of(self.x[i, j]) <= activity.latest_start
                       for i, project in enumerate(self.instance.projects)
                       for j, activity in enumerate(project.activities))

        # Precedence constraints
        self.model.add(end_before_start(self.x[i, j], self.x[i, j_prime])
                       for i, project in enumerate(self.instance.projects)
                       for j, activity in enumerate(project.activities)
                       for j_prime in activity.successors)

        # Resource constraints
        # Global renewable resources
        global_resource_usage = {}
        for k, resource_type in enumerate(self.instance.resource_types):
            if resource_type == 0:
                global_resource_usage[k] = sum(pulse(self.modes[i, j, m], activity.resource_req[m][k])
                                               for i, project in enumerate(self.instance.projects)
                                               for j, activity in enumerate(project.activities)
                                               for m in activity.modes
                                               if activity.resource_req[m][k] > 0)

        self.model.add(global_resource_usage[k] <= capacity
                       for k, capacity in enumerate(self.instance.resource_capacities)
                       if self.instance.resource_types[k] == 0)

        # Local renewable resources
        local_renewable_resource_usage = {}
        for k, resource_type in enumerate(self.instance.resource_types):
            if resource_type == 1:
                for i, project in enumerate(self.instance.projects):
                    local_renewable_resource_usage[i, k] = sum(pulse(self.modes[i, j, m], activity.resource_req[m][k])
                                                               for j, activity in enumerate(project.activities)
                                                               for m in activity.modes
                                                               if activity.resource_req[m][k] > 0)

        self.model.add(local_renewable_resource_usage[i, k] <= capacity
                       for i, project in enumerate(self.instance.projects)
                       for k, capacity in enumerate(project.resource_capacities)
                       if self.instance.resource_types[k] == 1)

        # Local nonrenewable resources
        local_nonrenewable_resource_usage = {}
        for k, resource_type in enumerate(self.instance.resource_types):
            if resource_type == 2:
                for i, project in enumerate(self.instance.projects):
                    local_nonrenewable_resource_usage[i, k] = sum(
                        presence_of(self.modes[i, j, m]) * activity.resource_req[m][k]
                        for j, activity in enumerate(project.activities)
                        for m in activity.modes
                        if activity.resource_req[m][k] > 0)

        self.model.add(local_nonrenewable_resource_usage[i, k] <= capacity
                       for i, project in enumerate(self.instance.projects)
                       for k, capacity in enumerate(project.resource_capacities)
                       if self.instance.resource_types[k] == 2)

        # objective function
        self.model.add(minimize(self._makespan_expression()))

    def solve(self, starting_heuristic=False, **params):
        """
        Solves the optimization model.

        Args:
            starting_heuristic (bool): Indicating if CP is solved to only obtain an initial solution
        Keyword Args:
            TimeLimit (int): Integer specifying the time limit for the solving process measured in seconds.
            OutputFlag (bool): Boolean indicating if the log file should be printed to the console during solving.
        """
        # Update solving parameters
        for key, val in params.items():
            self.params[key] = val
        if self.params["OutputFlag"]:
            self.model.set_parameters({'LogVerbosity': 'Normal'})
        else:
            self.model.set_parameters({'LogVerbosity': 'Quiet'})

        # Solve Model and collect solving statistics
        start_time = time.perf_counter()
        if starting_heuristic:
            callback = ProgressCallback(cp=self)
            self.model.add_solver_callback(callback)
            sol = self.model.solve(TimeLimit=self.params["TimeLimit"], Workers=self.params["Worker"])
            status = sol.get_solve_status()
            self.objective_bound = sol.get_objective_bound()
        else:
            solution_iterator = self.model.start_search(TimeLimit=self.params["TimeLimit"],
                                                        Workers=self.params["Worker"])
            for sol in solution_iterator:
                self.add_solution_to_pool(cp_solution=sol)
            self.objective_bound = solution_iterator.get_last_result().get_objective_bound()
            solution_iterator.end_search()
            status = solution_iterator.get_last_result().get_solve_status()

        if status == "Optimal":
            self.status = 2
        elif status == "Infeasible":
            self.status = 3
        self.runtime = time.perf_counter() - start_time

    def _makespan_expression(self):
        """
        Builds the total makespan expression: each project's completion time relative to its release
        date and critical path duration, summed across all projects. Shared by the objective function
        (populate_model) and add_upper_bound_constraint so the two stay consistent if the cost formula
        ever changes.

        Returns:
            docplex.cp.expression.CpoExpr: The makespan expression.
        """
        return sum([end_of(self.x[i, project.activities[-1].index]) -
                   project.release_date - project.critical_path_duration
                   for i, project in enumerate(self.instance.projects)])

    def add_upper_bound_constraint(self, upper_bound):
        """
        Adds a constraint on the upper bound of the objective function.

        Args:
            upper_bound (float): Upper bound for the objective function.
        """
        self.model.add(self._makespan_expression() <= upper_bound)

    def add_solution_to_pool(self, cp_solution):
        """
        Adds solution to solution pool.

        Args:
            cp_solution (docplex.cp.solution): Solution of the docplex.cp.model.CPOModel.
        """
        start_times = {}
        modes = {}
        for i, project in enumerate(self.instance.projects):
            for j, activity in enumerate(project.activities):
                for m in activity.modes:
                    if cp_solution.get_var_solution(self.modes[i, j, m]).is_present():
                        start_times[i, j] = cp_solution.get_var_solution(self.x[i, j]).start
                        modes[i, j] = m

        sol = Solution(instance=self.instance, start_times=start_times, modes=modes,
                       objective_value=cp_solution.get_objective_value())
        self.solution_pool.append(sol)
        self.status = 1
        if cp_solution.get_objective_value() < self.objective_value:
            self.solution = sol
            self.objective_value = sol.objective_value
