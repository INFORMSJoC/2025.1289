# Python Basics
import time

# Internal Dependencies
import src.Constants
from src.Interfaces import OptimizationModel
from src.Solution import Solution

# External Dependencies
from docplex.cp.model import start_of, CpoModel, interval_var, alternative, end_before_start, pulse, presence_of,\
    step_at_start, minimize, maximize


class CPSubproblem(OptimizationModel):
    """
    Subproblem for CP-based optimization-based bound tightening.

    Attributes:
        instance (Instance): Instance object representing the MRCMPSP instance.
        solution (Solution): Currently best known solution of the constraint program.
        solution_pool (List of Solution): Pool of solutions.
        objective_value (float): Objective value for currently best known solution.
        objective_bound (float): Currently best known bound for objective value.
        runtime (float): Runtime from last solve call.
        status (int): Status of the solving process (0:unsolved, 1:suboptimal, 2:optimal, 3:infeasible)
        project (Project): Project object representing the project corresponding to the subproblem.
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

        update_objective(activity_index, minimization=True):
            Updates the objective function for given activity and objective sense.

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
        super().__init__(instance=instance)
        self.project = project
        self.model = CpoModel()
        self.x = None
        self.modes = None
        self.objective_function = None
        self.params = {"TimeLimit": 3600, "OutputFlag": False}

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

        # Objective
        self.objective_function = minimize(start_of(self.x[self.project.activities[-1].index])
                                           - self.project.release_date - self.project.critical_path_duration)
        self.model.add(self.objective_function)

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

    def update_objective(self, activity_index, minimization=True):
        """
        Updates the objective function to minimize or maximize the start time of a given activity.

        Args:
            activity_index (int): Index of the activity for which the objective is updated.
            minimization (bool, optional): If True, minimizes the start time; otherwise maximizes it.
        """
        if minimization:
            new_objective = minimize(start_of(self.x[activity_index]))
        else:
            new_objective = maximize(start_of(self.x[activity_index]))
        self.model.replace_expression(self.objective_function, new_objective)
        self.objective_function = new_objective

    def solve(self, **params):
        """
        Solves the optimization model.

        Keyword Args:
            TimeLimit (int): Integer specifying the time limit for the solving process measured in seconds.
            OutputFlag (bool): Boolean indicating if the log file should be printed to the console during solving.
        """
        # Reset solving statistics and solutions
        self.status = 0
        self.solution_pool.clear()
        self.solution = None
        self.objective_value = src.Constants.INFINITY
        self.objective_bound = -src.Constants.INFINITY

        # Update solving parameters
        for key, val in params.items():
            self.params[key] = val

        # Solve Model and collect solving statistics
        start_time = time.perf_counter()
        solution_iterator = self.model.start_search(
            TimeLimit=self.params["TimeLimit"], Workers=1, RandomSeed=src.Constants.SEED,
            LogVerbosity="Normal" if self.params["OutputFlag"] else "Quiet")

        for sol in solution_iterator:
            self.add_solution_to_pool(cp_solution=sol)

        self.objective_bound = solution_iterator.get_last_result().get_objective_bound()
        status = solution_iterator.get_last_result().get_solve_status()
        if status == "Optimal":
            self.status = 2
        elif status == "Infeasible":
            self.status = 3
        self.runtime = time.perf_counter() - start_time

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

