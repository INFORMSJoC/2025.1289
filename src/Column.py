from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class Column:
    """
    Object representing a column (variable) of the restricted master problem.

    Attributes:
        index (int): Integer representing the index of the column.
        project_index (int): Index of the project corresponding to the column.
        global_resource_req (dict): Resource requirement for global resources, keyed by (resource, time).
        start_times (dict): Start time assignments, keyed by (project_index, activity_index).
        modes (dict): Mode assignments, keyed by (project_index, activity_index).
        costs (int): Costs of the column (i.e., coefficient in the objective function).
        stage (str or int): Stage of the solution procedure in which the column was generated.
    """

    index: int
    project_index: int
    global_resource_req: Dict[Tuple[int, int], int]
    start_times: Dict[Tuple[int, int], int]
    modes: Dict[Tuple[int, int], int]
    costs: int
    stage: str
