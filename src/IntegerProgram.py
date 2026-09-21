# Python Basics
import math

# External Dependencies
import gurobipy as gp
from gurobipy import GRB

# Internal Dependencies
import src.Constants
from src.Solution import Solution
from src.Interfaces import OptimizationModel


class IntegerProgram(OptimizationModel):
    """
    Integer program for an MRCMPSP instance.

    Attributes:
        instance (Instance): Instance object representing the MRCMPSP instance.
        solution (Solution): Currently best known solution of the constraint program.
        solution_pool (List of Solution): Pool of solutions.
        objective_value (float): Objective value for currently best known solution.
        objective_bound (float): Currently best known bound for objective value.
        runtime (float): Runtime from last solve call.
        status (int): Status of the solving process (0:unsolved, 1:suboptimal, 2:optimal, 3:infeasible)
        model (gurobipy.Model): Gurobi model.
        x (dict): Set of decision variables.
        params (dict): Keyword parameters for solving process.

    Methods:
        populate_model():
            Populates the optimization model with the MRCMPSP instance data.

        solve(**params):
            Solves the optimization model.

        add_solution_to_pool():
            Adds solution to solution pool.
    """

    def __init__(self, instance):
        """
        Initializes integer program.

        Args:
            instance (Instance): Instance object representing the MRCMPSP instance.
        """
        super().__init__(instance=instance)
        self.model = gp.Model()
        self.x = None
        self.runtime = None
        self.params = {"TimeLimit": 3600, "OutputFlag": True}

    def populate_model(self):
        """
        Populates the optimization model with the MRCMPSP instance data.
        """
        # Decision variables
        self.x = self.model.addVars([(i, j, m, t)
                                     for i, project in enumerate(self.instance.projects)
                                     for j, activity in enumerate(project.activities)
                                     for m in activity.modes
                                     for t in range(activity.earliest_start, activity.latest_start+1)],
                                    vtype=GRB.BINARY, name="x")
        # Constraints
        # Start every activity once in exactly one mode
        for i, project in enumerate(self.instance.projects):
            for j, activity in enumerate(project.activities):
                self.model.addConstr((gp.quicksum(self.x[i, j, m, t]
                                                  for m in activity.modes
                                                  for t in range(activity.earliest_start, activity.latest_start + 1))
                                      == 1),
                                     name=f"start_once[{i},{j}]")

        # Precedence constraints
        for i, project in enumerate(self.instance.projects):
            for j, activity in enumerate(project.activities):
                for j_prime in activity.successors:
                    self.model.addConstr((gp.quicksum((t + activity.duration[m])*self.x[i, j, m, t]
                                                      for m in activity.modes
                                                      for t in range(activity.earliest_start,
                                                                     activity.latest_start+1))
                                          <= gp.quicksum(t*self.x[i, j_prime, m, t]
                                                         for m in project.activities[j_prime].modes
                                                         for t in range(project.activities[j_prime].earliest_start,
                                                                        project.activities[j_prime].latest_start+1))),
                                         name=f"precedence[{i},{j},{j_prime}]")

        # Resource constraints
        # Global renewable resources constraints
        for k, capacity in enumerate(self.instance.resource_capacities):
            if self.instance.resource_types[k] == 0:
                for t in self.instance.planning_horizon:
                    self.model.addConstr((gp.quicksum(activity.resource_req[m][k]*self.x[i, j, m, s]
                                                      for i, project in enumerate(self.instance.projects)
                                                      for j, activity in enumerate(project.activities)
                                                      for m in activity.modes
                                                      for s in
                                                      range(max(activity.earliest_start, t-activity.duration[m]+1),
                                                            min(activity.latest_start, t)+1))
                                          <= capacity),
                                         name=f"global_resources[{k},{t}]")

        # Local renewable resource
        for i, project in enumerate(self.instance.projects):
            for k, capacity in enumerate(project.resource_capacities):
                if project.resource_types[k] == 1:
                    for t in self.instance.planning_horizon:
                        #if t >= project.release_date:
                        self.model.addConstr((gp.quicksum(activity.resource_req[m][k] * self.x[i, j, m, s]
                                                          for j, activity in enumerate(project.activities)
                                                          for m in activity.modes
                                                          for s in range(max(activity.earliest_start,
                                                                             t-activity.duration[m]+1),
                                                                         min(activity.latest_start, t)+1))
                                              <= capacity),
                                             name=f"local_renewable_resources[{i},{k},{t}]")

        # Local nonrenewable resources constraints
        for i, project in enumerate(self.instance.projects):
            for k, capacity in enumerate(project.resource_capacities):
                if project.resource_types[k] == 2:
                    self.model.addConstr((gp.quicksum(activity.resource_req[m][k] * self.x[i, j, m, t]
                                                      for j, activity in enumerate(project.activities)
                                                      for m in activity.modes
                                           for t in range(activity.earliest_start, activity.latest_start+1))
                                          <= capacity),
                                         name=f"local_nonrenewable_resources[{i},{k}]")

        # Objective function
        self.model.setObjective(gp.quicksum((t-project.release_date-project.critical_path_duration)
                                            * self.x[i, project.activities[-1].index, m, t]
                                            for i, project in enumerate(self.instance.projects)
                                            for m in project.activities[-1].modes
                                            for t in range(project.activities[-1].earliest_start,
                                                           project.activities[-1].latest_start + 1)
                                            ),
                                sense=GRB.MINIMIZE)

    def solve(self, **params):
        """
        Solves the optimization model.

        Keyword Args:
            TimeLimit (int): Integer specifying the time limit for the solving process measured in seconds.
            OutputFlag (bool): Boolean indicating if the log file should be printed to the console during solving.
        """
        # Update parameters
        for key, val in params.items():
            self.params[key] = val
        if self.params["OutputFlag"]:
            self.model.setParam("OutputFlag", 1)
        else:
            self.model.setParam("OutputFlag", 0)
        self.model.setParam("TimeLimit", self.params["TimeLimit"])
        self.model.setParam("Seed", src.Constants.SEED)

        # Solve Model and collect solving statistics
        self.model.optimize()
        for i in range(self.model.SolCount):
            self.model.setParam(GRB.Param.SolutionNumber, i)
            self.add_solution_to_pool()
        if self.model.Status in [2, 3]:
            self.status = self.model.Status
        if self.status in [1, 2]:
            self.objective_bound = math.ceil(self.model.ObjBound - src.Constants.OPTIMALITY_TOLERANCE)
        self.runtime = self.model.Runtime

    def add_solution_to_pool(self):
        """
        Adds solution to solution pool.
        """
        start_times = {}
        modes = {}
        vals = self.model.getAttr("Xn", self.x)
        for i, project in enumerate(self.instance.projects):
            for j, activity in enumerate(project.activities):
                m, t = next((m, t) for m in activity.modes
                            for t in range(activity.earliest_start, activity.latest_start + 1)
                            if vals[i, j, m, t] > src.Constants.INTEGRALITY_TOLERANCE)
                start_times[i, j] = t
                modes[i, j] = m

        sol = Solution(instance=self.instance, start_times=start_times, modes=modes,
                       objective_value=self.model.PoolObjVal)
        self.solution_pool.append(sol)
        self.status = 1

        if self.model.PoolObjVal < self.objective_value:
            self.solution = sol
            self.objective_value = sol.objective_value
