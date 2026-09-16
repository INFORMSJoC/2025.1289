# External Dependencies
import pandas as pd


class Solution:
    """
    Solution (schedule) to an MRCMPSP instance.

    Attributes:
        instance (Instance): Instance object representing the MRCMPSP instance.
        start_times (dict): Dictionary containing the start times of the solution.
        modes (dict): Dictionary containing the mode assignments of the solution.
        objective_value (float): Objective function value of the solution.
        projects (list of Project): List of projects for which the solution is given.

    Methods:
        create_results_df():
            Returns the solution as a data frame.

    Note:
        By default the list of Projects contains all projects of the instance.
        However, for partial solutions the corresponding projects must be given explicitly.
    """

    def __init__(self, instance, start_times, modes, objective_value, projects=None):
        """
        Initializes the solution.

        Args:
            instance (Instance): Instance object representing the MRCMPSP instance.
            start_times (dict): Dictionary containing the start times of the solution.
            modes (dict): Dictionary containing the mode assignments of the solution.
            objective_value (float): Objective function value of the solution.
            projects (list of Project, optional): List of projects for which the solution is given.
        """
        self.instance = instance
        self.start_times = start_times
        self.modes = modes
        self.objective_value = objective_value
        if projects is None:
            self.projects = self.instance.projects
        else:
            self.projects = projects

    def create_results_df(self):
        """
        Returns the solution as a data frame.

        Returns:
             pandas.DataFrame(): Solution in a format of a pandas data Frame.
        """
        project_col = []
        activity_col = []
        mode_col = []
        start_time_col = []
        for i, project in enumerate(self.projects):
            for j, activity in enumerate(project.activities):
                project_col.append(i)
                activity_col.append(j)
                mode_col.append(self.modes[project.index, j])
                start_time_col.append(self.start_times[project.index, j])

        return pd.DataFrame({"Project": project_col, "Activity": activity_col,
                             "Mode": mode_col, "Start_Time": start_time_col})
