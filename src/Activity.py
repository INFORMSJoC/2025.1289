from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Activity:
    """
    Represents an activity.

    Attributes:
        index (int): Index of the activity.
        modes (list of int, optional): Modes available to process the activity.
        duration (list of int, optional): Time required to complete the activity.
        earliest_start (int, optional): Earliest time of the activity.
        latest_start (int, optional): Latest time of the activity.
        resource_req (nested list of int, optional): Requirement for resources.
        successors (list of int, optional): Activities that depend on the completion of this activity.
        predecessors (list of int, optional): Activities that must be completed before this activity can start.
    """

    index: int
    modes: Optional[List[int]] = None
    duration: Optional[List[int]] = None
    earliest_start: Optional[int] = None
    latest_start: Optional[int] = None
    resource_req: Optional[List[List[int]]] = None
    successors: Optional[List[int]] = None
    predecessors: Optional[List[int]] = None

    def to_dict(self):
        """
        Returns a dictionary representation of the activity.

        Returns:
            dict: A dictionary containing the attributes of the activity.
        """
        activity_dict = {"index": self.index,
                         "modes": self.modes,
                         "duration": self.duration,
                         "earliest_start": self.earliest_start,
                         "latest_start": self.latest_start,
                         "resource_requirement": self.resource_req,
                         "predecessors": self.predecessors,
                         "successors": self.successors}

        return activity_dict

    @classmethod
    def from_dict(cls, d):
        """
        Creates an Activity from its dictionary representation (as produced by to_dict()).

        Args:
            d (dict): Dictionary representation of the activity.

        Returns:
            Activity: The reconstructed activity.
        """
        return cls(index=d["index"], modes=d["modes"], duration=d["duration"],
                  earliest_start=d["earliest_start"], latest_start=d["latest_start"],
                  resource_req=d["resource_requirement"], predecessors=d["predecessors"],
                  successors=d["successors"])
