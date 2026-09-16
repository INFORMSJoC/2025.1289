from dataclasses import dataclass
from typing import List, Optional

from src.Activity import Activity


@dataclass
class Project:
    """
    Represents a project consisting of activities.

    Attributes:
        index (int): Index of the project.
        release_date (int, optional): Release date of the project.
        critical_path_duration (int, optional): Critical path duration of the project.
        resource_types (list of int, optional): Integer representing type of resource (0: global, 1: local
            renewable, 2: local non-renewable).
        resource_capacities (list of int, optional): Capacity of resources (-1 indicating a global resource).
        activities (list of Activity, optional): List of activities in the project. The last element is
            treated as the project's sink/terminal activity.

    Methods:
        to_dict():
            Returns a dictionary representation of the project object.

        from_dict(d):
            Creates a Project from its dictionary representation.
    """

    index: int
    release_date: Optional[int] = None
    critical_path_duration: Optional[int] = None
    resource_types: Optional[List[int]] = None
    resource_capacities: Optional[List[int]] = None
    activities: Optional[List[Activity]] = None

    def to_dict(self):
        """
        Returns a dictionary representation of the project object.

        Returns:
            dict: A dictionary containing the attributes of the project, including its activities.
        """
        return {"index": self.index,
               "release_date": self.release_date,
               "critical_path_duration": self.critical_path_duration,
               "resource_types": self.resource_types,
               "resource_capacities": self.resource_capacities,
               "activities": [activity.to_dict() for activity in self.activities]}

    @classmethod
    def from_dict(cls, d):
        """
        Creates a Project from its dictionary representation (as produced by to_dict()).

        Args:
            d (dict): Dictionary representation of the project.

        Returns:
            Project: The reconstructed project.
        """
        return cls(index=d["index"], release_date=d["release_date"],
                  critical_path_duration=d["critical_path_duration"],
                  resource_types=d["resource_types"], resource_capacities=d["resource_capacities"],
                  activities=[Activity.from_dict(a) for a in d["activities"]])
