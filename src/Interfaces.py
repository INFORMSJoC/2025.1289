# Python Basics
import abc

# Internal Dependencies
import src.Constants


class OptimizationModel(abc.ABC):
    """
    Base class for optimization models.

    Attributes:
        instance (Instance): Instance object representing the MRCMPSP instance.
        solution (Solution): Currently best known solution of the constraint program.
        solution_pool (List of Solution): Pool of solutions.
        objective_value (float): Objective value for currently best known solution.
        objective_bound (float): Currently best known bound for objective value.
        runtime (float): Runtime from last solve call.
        status (int): Status of the solving process (0:unsolved, 1:suboptimal, 2:optimal, 3:infeasible)

    Methods:
        populate_model():
            Populates the optimization model with the MRCMPSP instance data.

        solve(**params):
            Solves the optimization model.
    """

    def __init__(self, instance):
        """
        Initializes OptimizationModel object.

        Args:
            instance (Instance): Instance object representing the MRCMPSP instance.
        """
        self.instance = instance
        self.objective_value = src.Constants.INFINITY
        self.objective_bound = -src.Constants.INFINITY
        self.solution = None
        self.solution_pool = []
        self.runtime = None
        self.status = 0

    @abc.abstractmethod
    def populate_model(self):
        """
        Populates the optimization model with the MRCMPSP instance data.
        """
        pass

    @abc.abstractmethod
    def solve(self, **params):
        """
        Solves the optimization model.
        """
        pass


class PricingProblem(OptimizationModel):
    """
    Base class for pricing problems.

    Attributes:
        instance (Instance): Instance object representing the MRCMPSP instance.
        solution (Solution): Currently best known solution of the constraint program.
        solution_pool (List of Solution): Pool of solutions.
        objective_value (float): Objective value for currently best known solution.
        objective_bound (float): Currently best known bound for objective value.
        runtime (float): Runtime from last solve call.
        project (Project): Project object representing the project corresponding to the pricing problem.
        is_infeasible (bool): Boolean indicating if the pricing problem is currently infeasible.

    Methods:
        update_objective(duals_i, duals_k_t):
            Updates the objective function for given dual values.
        set_starting_solution(column=None):
            Define starting solution for warm start.
    """

    def __init__(self, instance, project):
        """
        Initializes PricingProblem object.

        Args:
            instance (Instance): Instance object representing the MRCMPSP instance.
            project (Project): Project object representing the project corresponding to the pricing problem.
        """
        super().__init__(instance=instance)
        self.project = project
        self.is_infeasible = False

    @abc.abstractmethod
    def update_objective(self, duals_i, duals_k_t):
        """
        Updates the objective function for given dual values.

        Args:
            duals_i (numpy.array): Array of dual values corresponding to convexity constraints.
            duals_k_t (numpy.array): Array of dual values corresponding to global resource constraints.
        """
        pass

    @abc.abstractmethod
    def set_starting_solution(self, column=None):
        """
        Define starting solution for warm start.

        Args:
            column (Column, optional): Column from which starting solution is retrieved.

        Note:
            If no column is given the best known solution from the last solve is used as starting solution.
        """
        pass