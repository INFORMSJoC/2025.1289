# Python Basics
import json
from pathlib import Path

# Internal Dependencies
from src.Project import Project


class Instance:
    """
    Represents an MRCMPSP instance.

    Attributes:
        name (str, optional): The name of the instance.
        planning_horizon (list of int, optional): Discrete time horizon.
        resource_types (list of int, optional): Integer representing type of resource (0: global, 1: local
            renewable, 2: local non-renewable).
        resource_capacities (list of int, optional): Capacity of global resources (-1 indicating a local resource).
        projects (list of Project, optional): List of projects.

    Methods:
        to_dict():
            Returns a dictionary representation of the MRCMPSP instance.

        save_as_json(path=""):
            Serializes the MRCMPSP instance object to a JSON file and saves it to the specified path.

        from_json(path):
            Creates an Instance from a JSON file.
    """

    def __init__(self, name=None, planning_horizon=None, resource_types=None, resource_capacities=None,
                 projects=None):
        """
        Initializes an Instance object with the provided parameters.

        Args:
            name (str, optional): The name of the instance.
            planning_horizon (list of int, optional): Discrete time horizon.
            resource_types (list of int, optional): Integer representing type of resource (0: global, 1: local
                renewable, 2: local non-renewable).
            resource_capacities (list of int, optional): Capacity of global resources (-1 indicating a local resource).
            projects (list of Project, optional): List of projects.
        """
        self.name = name
        self.planning_horizon = planning_horizon
        self.resource_types = resource_types
        self.resource_capacities = resource_capacities
        self.projects = projects

    def to_dict(self):
        """
        Returns a dictionary representation of the MRCMPSP instance.

        Returns:
            dict: A dictionary containing the attributes of the MRCMPSP instance.
        """
        instance_dict = {"name": self.name,
                         "planning_horizon": self.planning_horizon,
                         "resource_types": self.resource_types,
                         "resource_capacities": self.resource_capacities,
                         "projects": [project.to_dict() for project in self.projects]}

        return instance_dict

    def save_as_json(self, path=""):
        """
        Serializes the MRCMPSP instance object to a JSON file and saves it to the specified path.

        Args:
            path (str, optional): The file path where the instance will be saved in JSON format.
        """
        json_data = self.to_dict()
        with open(Path(path) / f'{self.name}.json', 'w') as outfile:
            json.dump(json_data, outfile, indent=3)

    @classmethod
    def from_json(cls, path):
        """
        Creates an Instance from a JSON file.

        Args:
            path (str): The file path (without the .json suffix) from which the instance data will be read.

        Returns:
            Instance: The instance populated with the data read from the JSON file.
        """
        with open(Path(f'{path}.json')) as f:
            data = json.load(f)
        return cls(name=data["name"], planning_horizon=data["planning_horizon"],
                  resource_types=data["resource_types"], resource_capacities=data["resource_capacities"],
                  projects=[Project.from_dict(p) for p in data["projects"]])
