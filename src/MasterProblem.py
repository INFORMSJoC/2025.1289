# External Dependencies
import random

import gurobipy as gp
from gurobipy import GRB
import numpy as np

# Internal Dependencies
from src.Interfaces import OptimizationModel


class MasterProblem(OptimizationModel):
    """
    Restricted master problem for column generation.

    Attributes:
        instance (Instance): Instance object representing the MRCMPSP instance.
        solution (Solution): Currently best known solution of the constraint program.
        solution_pool (List of Solution): Pool of solutions.
        objective_value (float): Objective value for currently best known solution.
        objective_bound (float): Currently best known bound for objective value.
        runtime (float): Runtime from last solve call.
        status (int): Status of the solving process (0:unsolved, 1:suboptimal, 2:optimal, 3:infeasible)
        model (gurobipy.Model): Gurobi model.
        column_vars (dict): Set of decision variables (columns).
        dummy_vars (dict): Set of dummy variables (columns).
        convexity_cons (dict): Set of convexity constraints.
        global_resource_cons (dict): Set of global resource constraints.
        params (dict): Keyword parameters for solving process.

    Methods:
        populate_model():
            Populates the optimization model with the MRCMPSP instance data.

        solve(**params):
            Solves the optimization model.

        add_column(column):
            Adds a new column to the restricted master problem.

        retrieve_duals():
            Retrieves the dual values of the current solution
    """

    def __init__(self, instance):
        """
        Initializes restricted master program.

        Args:
            instance (Instance): Instance object representing the MRCMPSP instance.
        """
        super().__init__(instance=instance)
        self.model = gp.Model()
        self.column_vars = {}
        self.dummy_vars = None
        self.convexity_cons = []
        self.global_resource_cons = []
        self.params = {"TimeLimit": 3600, "OutputFlag": False}

    def populate_model(self):
        """
        Populates the optimization model with the MRCMPSP instance data.
        """
        # Decision variables
        self.dummy_vars = self.model.addVars([i for i, project in enumerate(self.instance.projects)],
                                             lb=0, ub=1, vtype=GRB.CONTINUOUS, name="phi")

        # convexity constraints
        for i, project in enumerate(self.instance.projects):
            self.convexity_cons.append(self.model.addConstr((self.dummy_vars[i] >= 1.0), name=f"convexity_cons{i}"))

        # global resource constraints
        # Declared empty (LHS is always 0) here; each column contributes its actual usage
        # via addTerms in add_column() as it is generated during column generation.
        for k, capacity in enumerate(self.instance.resource_capacities):
            resource_cons = []
            if self.instance.resource_types[k] == 0:
                for t in self.instance.planning_horizon:
                    resource_cons.append(self.model.addConstr((gp.quicksum(0 * t * self.dummy_vars[i]
                                                                           for i, project in
                                                                           enumerate(self.instance.projects))
                                                               <= capacity),
                                                              name=f"global_resource_cons[{k},{t}]"))
            self.global_resource_cons.append(resource_cons)

        # objective function
        self.model.setObjective(gp.quicksum(self.instance.planning_horizon[-1] * 10 * self.dummy_vars[i]
                                            for i, project in enumerate(self.instance.projects)),
                                sense=GRB.MINIMIZE)

    def solve(self, **params):
        """
        Solves the optimization model.

        Keyword Args:
            TimeLimit (int): Integer specifying the time limit for the solving process measured in seconds.
            OutputFlag (bool): Boolean indicating if the log file should be printed to the console during solving.
        """
        # Update solving parameters
        for key, val in params.items():
            self.params[key] = val
        if self.params["OutputFlag"]:
            self.model.setParam("OutputFlag", 1)
        else:
            self.model.setParam("OutputFlag", 0)
        self.model.setParam("TimeLimit", self.params["TimeLimit"])

        self.objective_value = 0
        # Solve Model and update status
        self.model.reset()
        self.model.optimize()
        if self.model.Status in [0, 2, 3]:
            self.status = self.model.Status
        else:
            self.status = 1
        if self.status != 3:
            self.objective_value = self.model.ObjVal

    def add_column(self, column):
        """
        Adds a new column to the restricted master problem.

        Args:
            column (Column): Column to be added to the restricted master problem.
        """
        c = gp.Column()
        c.addTerms(1.0, self.convexity_cons[column.project_index])
        for key, req in column.global_resource_req.items():
            if self.instance.resource_types[key[0]] == 0:
                if req > 0:
                    c.addTerms(req, self.global_resource_cons[key[0]][key[1]])

        self.column_vars[column.index] = self.model.addVar(vtype=GRB.CONTINUOUS, lb=0,
                                                           obj=column.costs, column=c,
                                                           name=f"column[{column.index}]")

    def retrieve_duals(self):
        """
        Retrieves the dual values of the current solution

        Returns:
             duals_i: numpy.array
                Array of dual values corresponding to convexity constraints.
            duals_k_t: numpy.array
                Array of dual values corresponding to global resource constraints.
        """
        duals_i = np.array(self.model.getAttr(GRB.Attr.Pi, self.convexity_cons), dtype=np.float64)
        duals_k_t = []
        for k, capacity in enumerate(self.instance.resource_capacities):
            if self.instance.resource_types[k] == 0:
                duals_k_t.append(self.model.getAttr(GRB.Attr.Pi, self.global_resource_cons[k]))
        duals_k_t = np.array(duals_k_t, dtype=np.float64)

        return duals_i, duals_k_t
