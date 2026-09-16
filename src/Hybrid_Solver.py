# Python Basics
import json
import os
import time
import random
import multiprocessing
import math
from pathlib import Path

# Internal Dependencies
import src.Constants
from src.ConstraintProgram import ConstraintProgram
from src.CPSubproblem import CPSubproblem
from src.Column import Column
from src.MasterProblem import MasterProblem
from src.PricingProblemCP import PricingProblemCP
from src.PricingProblemIP import PricingProblemIP

# External Dependencies
from docplex.cp.model import start_of, presence_of
import pandas as pd

PHASES = ["CP-OBBT", "CP-LNS", "CG-CP", "CG-IP"]
STAGE_OBBT, STAGE_LNS, STAGE_CG_CP, STAGE_CG_IP = PHASES


class Pricer(multiprocessing.Process):
    """
    Pricer facilitates process of running pricing problems.

    Attributes:
        name (str): Name of the process.
        instance (Instance): Instance object representing the MRCMPSP instance.
        index (int): Index of pricing problem.
        model_type (str): Model type 'CP or 'IP'.
        lock (multiprocessing.Manger.Lock): Lock for thread safety during multiprocessing.
        queue (multiprocessing.Manger.Queue): Queue for communicating between multiple processes.
        start_event (multiprocessing.Event): Event signaling start of solving pricing problem.
        stop_event (multiprocessing.Event): Event signaling end of solving pricing problem.
        master_event (multiprocessing.Event): Event signaling resolving of master problem.
        dual_queue (multiprocessing.Manger.Queue): Queue for sending dual values between multiple processes.
        column_event (multiprocessing.Event): Event signaling the discovery of new columns.
        iteration (int): Column generation iteration.
        deadline (float, optional): Time stamp (perf_counter) by which the pricing problem must terminate.

    Methods:
        run():
            Initializes and runs the pricing problem.

    """
    def __init__(self, name, instance, index, model_type, lock, queue, dual_queue, start_event, stop_event,
                 master_event, column_event, iteration, deadline=None):
        """
        Initializes Pricer object.

        Args:
            name (str): Name of the process.
            instance (Instance): Instance object representing the MRCMPSP instance.
            index (int): Index of pricing problem.
            model_type (str): Model type 'CP or 'IP'.
            lock (multiprocessing.Manger.Lock): Lock for thread safety during multiprocessing.
            queue (multiprocessing.Manger.Queue): Queue for communicating between multiple processes.
            dual_queue (multiprocessing.Manger.Queue): Queue for sending dual values between multiple processes.
            start_event (multiprocessing.Event): Event signaling start of solving pricing problem.
            stop_event (multiprocessing.Event): Event signaling end of solving pricing problem.
            master_event (multiprocessing.Event): Event signaling resolving of master problem.
            column_event (multiprocessing.Event): Event signaling the discovery of new columns.
            iteration (int): Column generation iteration.
            deadline (float, optional): Time stamp (perf_counter) by which the pricing problem must terminate.
        """
        super().__init__()
        self.name = name
        self.instance = instance
        self.index = index
        self.model_type = model_type
        self.lock = lock
        self.queue = queue
        self.start_event = start_event
        self.stop_event = stop_event
        self.master_event = master_event
        self.dual_queue = dual_queue
        self.column_event = column_event
        self.iteration = iteration
        self.deadline = deadline

    def run(self):
        """
        Initializes and runs the pricing problem.
        """
        # Initialize pricing problem
        pricing_problem = None
        if self.model_type == "CP":
            pricing_problem = PricingProblemCP(instance=self.instance, project=self.instance.projects[self.index])
            pricing_problem.populate_model()
        else:
            pricing_problem = PricingProblemIP(instance=self.instance, project=self.instance.projects[self.index])
            pricing_problem.populate_model()
            pricing_problem.model.setParam("OutputFlag", 1)

        # Solve pricing problem
        while True:
            self.start_event.wait()
            self.stop_event.clear()

            # Retrieve dual values
            duals_i = None
            duals_k_t = None
            with self.lock:
                duals_i, duals_k_t = self.dual_queue.get()
                self.dual_queue.put((duals_i, duals_k_t))

            # Update and Solve pricing problem
            pricing_problem.update_objective(duals_i=duals_i, duals_k_t=duals_k_t)
            if self.model_type == "CP":
                restart = True
                restart_num = 0
                while restart:
                    try:
                        pricing_problem.solve(event=self.column_event, master_iteration=self.iteration,
                                                TimeLimit=(len(pricing_problem.project.activities)-2))
                        restart = False
                    except Exception as e:
                        restart_num += 1
                        restart = True
                        base_delay = 0.1
                        print(f"pricer {self.index} ({self.model_type}) solve failed, retrying "
                              f"(attempt {restart_num}): {e}")
                        time.sleep(base_delay*math.pow(2, restart_num-1))
            else:
                remaining_time = max(self.deadline - time.perf_counter(), 0) if self.deadline is not None \
                    else src.Constants.ZETA_CG
                pricing_problem.solve(event=self.column_event, counter=self.iteration, bounding="IP",
                                      TimeLimit=remaining_time, deadline=self.deadline, OutputFlag=False)

            if self.model_type == "CP":
                with self.lock:
                    if pricing_problem.objective_value < -src.Constants.EPSILON:
                        for solution in pricing_problem.solution_pool:
                            self.queue.put((pricing_problem.project.index, solution))
                            self.column_event.set()
            else:
                with self.lock:
                    for solution in pricing_problem.solution_pool:
                        self.queue.put((pricing_problem.objective_bound, self.index, solution))
                    self.queue.put((pricing_problem.objective_bound, self.index, None))

            # Set events
            self.start_event.clear()
            self.stop_event.set()
            self.master_event.set()


def obbt_worker(instance, project_index):
    """
    Presolves a given project of an MRCMPSP instances via CP-OBBT.

    Args:
        instance (Instance): Instance object representing the MRCMPSP instance.
        project_index (int): Index of project to be presolved.

    Returns:
        Project: Presolved project object.
        list of Solutions: Set of solutions for presolved project.
    """
    solution_pool = []
    cp = CPSubproblem(instance=instance, project=instance.projects[project_index])
    cp.populate_model()
    for j, activity in enumerate(instance.projects[project_index].activities):
        # Minimize start time
        cp.update_objective(activity_index=j)
        cp.solve(TimeLimit=src.Constants.ALPHA_OBBT, OutputFlag=False)
        if activity.earliest_start < cp.objective_bound:
            print(f"OBBT strengthened earliest start of activity {project_index, j} "
                  f"from {activity.earliest_start} to {cp.objective_bound}")
            activity.earliest_start = cp.objective_bound
        for sol in cp.solution_pool:
            solution_pool.append(sol)

        # Maximize start time (skipped due to accerlation strategy: "unbounded direction")
        #cp.update_objective(activity_index=j, minimization=False)
        #cp.solve(TimeLimit=TIME_PER_OBBT_SUBPROBLEM, OutputFlag=False)
        #if activity.latest_start > cp.objective_bound:
        #    print(f"activity {project_index, j} LS: {activity.latest_start} -> {cp.objective_bound}")
        #    activity.latest_start = cp.objective_bound
        #for sol in cp.solution_pool:
        #    solution_pool.append(sol)

    return instance.projects[project_index], solution_pool


def lns_worker(instance, solution, neighborhood, queue, lock):
    """
    Destroys and repairs solution for given neighborhood.

    Args:
        instance (Instance): Instance object representing the MRCMPSP instance.
        solution (Solution): Solution to be destroyed and repaired.
        neighborhood (list of int): Neighborhood to be explored.
        queue (multiprocessing.Manager.Queue): Queue the resulting solution pool is put on.
        lock (multiprocessing.Manager.Lock): Lock for thread safety during multiprocessing.
    """
    cp = ConstraintProgram(instance=instance)
    cp.populate_model()
    for key, val in solution.start_times.items():
        if key[0] not in neighborhood:
            cp.model.add(start_of(cp.x[key]) == val)
    for key, val in solution.modes.items():
        if key[0] not in neighborhood:
            cp.model.add(presence_of(cp.modes[key[0], key[1], val]) == 1)
    print(f"Start exploring neighborhood {neighborhood}")
    cp.solve(TimeLimit=src.Constants.GAMMA_LNS, OutputFlag=False, Worker=1)
    print(f"Finished exploring neighborhood {neighborhood}")
    with lock:
        queue.put((neighborhood, cp.solution_pool))


class Hybrid_Solver:
    """
    Hybrid solver facilitates solving process of an MRCMPS instance via CP-based Dantzig-Wolfe Decomposition.

    Attributes:
        instance (Instance): Instance object representing the MRCMPSP instance.
        lower_bound (float): Currently best known lower bound.
        upper_bound (float): Currently best known upper bound.
        gap (float): Optimality gap.
        runtime (multiprocessing.Value): Runtime in seconds.
        solution (Solution): Currently best known solution.
        column_pool (dict): Pool of columns.
        start_time (float): Start time of last solving call.
        log (pandas.DataFrame): Log information of solving process.
        log_dir (pathlib.Path): Directory results (logs and summaries) are written to.
        log_path (pathlib.Path): Path of the current run's log CSV file.
        summary_path (pathlib.Path): Path of the current run's summary JSON file.
        run_start_time (float): Start time of the current CP_DWD() call.
        phase_durations (dict): Runtime in seconds spent in each phase.
        unique_columns_per_stage (dict): Number of unique columns generated per stage.
        total_columns_per_stage (dict): Total number of columns generated per stage.
        seen_column_signatures (set): Signatures of all columns generated so far, used to detect duplicates.
        worker_pool (multiprocessing.Pool): Pool of workers for multiprocessing.
        manager (multiprocessing.Manager): Multiprocessing manager.
        lock (multiprocessing.Manger.Lock): Lock for thread safety during multiprocessing.
        queue (multiprocessing.Manger.Queue): Queue for communicating between multiple processes.

    Methods:
        CP_DWD(**params):
            Solves the MRCMPSP data via CP-based Dantzig-Wolfe Decomposition.

        add_column_to_pool(solution_pool, projects, stage):
            Extracts columns from solution pool for a given set of projects and adds them to the column pool.

        logging(stage):
            Updates and prints logging information.

        Propagate(bound=None):
            Propagates the time windows of the activities for given or currently best known upper bound.

        CP_OBBT():
            Presolves the MRCMPSP instances via CP-based optimization-based bound tightening.

        select_neighborhood(size, tabu_list):
            Selects a neighborhood not in the tabu list yet.

        CP_LNS(time_limit):
            Performs a CP-based large neighborhood search for a given time limit.

        CP_IP_CG_Parallel(time_limit=3600, **params):
            Solves the linear relaxation of the master problem via column generation.

        build_summary():
            Builds the end-of-run summary: time spent, and unique/total columns generated, per phase.

    Note:
        CP_DWD, CP_OBBT, CP_LNS, and CP_IP_CG deliberately use CP_ALLCAPS naming to mirror the
        algorithm names used in the accompanying paper, unlike the snake_case used elsewhere in
        this class and file.
    """
    def __init__(self, instance):
        """
        Initializes the hybrid solver.

        Args:
            instance (Instance): Instance object representing the MRCMPSP instance.
        """

        # Problem Instance
        self.instance = instance

        # Solving Statistics
        self.lower_bound = 0
        self.upper_bound = src.Constants.INFINITY
        self.gap = None
        self.runtime = multiprocessing.Value("i", 0)
        self.solution = None
        self.column_pool = {}
        self.start_time = None
        self.log = pd.DataFrame(columns=["Stage", "UB", "LB", "Gap", "Time", "#Columns"])

        # Logging and column-stage statistics
        self.log_dir = Path(__file__).resolve().parent.parent / "results"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = None
        self.summary_path = None
        self.run_start_time = None
        self.phase_durations = {}
        self.unique_columns_per_stage = {}
        self.total_columns_per_stage = {}
        self.seen_column_signatures = set()

        # Infrastructure for parallel computing
        self.worker_pool = multiprocessing.Pool(processes=os.cpu_count())
        self.manager = multiprocessing.Manager()
        self.lock = self.manager.Lock()
        self.queue = self.manager.Queue()

    def CP_DWD(self, **params):
        """
        Solves the MRCMPSP data via CP-based Dantzig-Wolfe Decomposition.

        Keyword Args:
            TimeLimit (float): Time limit in seconds for the CP-IP-CG phase.
            DisableOBBT (bool): If True, skips the CP-OBBT presolve phase. Defaults to False.
            DisableLNS (bool): If True, skips the CP-LNS primal heuristic phase. Defaults to False.
        """
        disable_obbt = params.get("DisableOBBT", False)
        disable_lns = params.get("DisableLNS", False)

        # Initialize
        run_name = self.instance.name
        self.log_path = self.log_dir / f"{run_name}_log.csv"
        self.summary_path = self.log_dir / f"{run_name}_summary.json"
        self.run_start_time = time.perf_counter()
        self.lower_bound = 0
        self.upper_bound = src.Constants.INFINITY
        self.gap = None
        self.runtime.value = 0
        self.solution = None
        self.column_pool = {}
        self.phase_durations = {}
        self.unique_columns_per_stage = {}
        self.total_columns_per_stage = {}
        self.seen_column_signatures = set()
        self.start_time = time.perf_counter()
        self.logging(stage="Initialize")

        # Presolve: CP-OBBT to tighten time windows
        self.start_time = time.perf_counter()
        if not disable_obbt:
            self.CP_OBBT()
            self.phase_durations["CP-OBBT"] = time.perf_counter() - self.start_time
            self.logging(stage=STAGE_OBBT)

        # Primal Heuristic: CP-based large neighborhood search to improve solution
        if not disable_lns:
            lns_phase_start = time.perf_counter()
            self.CP_LNS(time_limit=src.Constants.TIME_LIMIT_LNS)
            self.phase_durations["CP-LNS"] = time.perf_counter() - lns_phase_start
            self.logging(stage=STAGE_LNS)
        self.Propagate()

        if abs(self.upper_bound - self.lower_bound) > src.Constants.EPSILON:
            # Column Generation: CP-IP-CG to compute lower bound
            print(f"Remaining Time for CP-IP-CG {params['TimeLimit'] - (time.perf_counter() - self.start_time)}")
            print(params["TimeLimit"], (time.perf_counter() - self.start_time))
            self.CP_IP_CG(time_limit=params["TimeLimit"])
            self.logging(stage="CP-IP-CG")

        print(self.log)
        summary = self.build_summary()
        with open(self.summary_path, "w") as f:
            json.dump(summary, f, indent=4)
        print(json.dumps(summary, indent=2))

    def add_column_to_pool(self, solution_pool, projects, stage):
        """
        Extracts columns from solution pool for a given set of projects and adds them to the column pool.

        Args:
            solution_pool (list of Solution): Pool of solutions.
            projects (List of Project): List of projects for which columns are extracted.
            stage (str or int): Stage of the solution procedure in which the columns were generated.
        """
        columns = []
        for project in projects:
            for solution in solution_pool:
                # container for resource requirements
                resource_req = {(k, t): 0 for k, resource_type in enumerate(project.resource_types)
                                if resource_type == 0
                                for t in range(project.release_date, project.activities[-1].latest_start + 1)}

                start_times = {}
                modes = {}
                for j, activity in enumerate(project.activities):
                    start_time = solution.start_times[project.index, j]
                    m = solution.modes[project.index, j]
                    start_times[project.index, j] = start_time
                    modes[project.index, j] = m
                    for k, resource_type in enumerate(project.resource_types):
                        if resource_type == 0:
                            for t in range(start_time, start_time + activity.duration[m]):
                                resource_req[k, t] += activity.resource_req[m][k]

                costs = solution.start_times[project.index, project.activities[-1].index] \
                        - project.release_date - project.critical_path_duration

                signature = (project.index, tuple(sorted(start_times.items())), tuple(sorted(modes.items())))
                self.total_columns_per_stage[stage] = self.total_columns_per_stage.get(stage, 0) + 1
                if signature not in self.seen_column_signatures:
                    self.seen_column_signatures.add(signature)
                    self.unique_columns_per_stage[stage] = self.unique_columns_per_stage.get(stage, 0) + 1

                column = Column(index=len(self.column_pool.keys()), project_index=project.index,
                                global_resource_req=resource_req, start_times=start_times,
                                modes=modes, costs=costs, stage=stage)
                columns.append(column)
                self.column_pool[column.index] = column

    def logging(self, stage):
        """
        Updates and prints logging information.

        Args:
            stage (str): Current stage of the solving process.
        """
        self.runtime.value = int(time.perf_counter()-self.run_start_time)
        self.lower_bound = math.ceil(self.lower_bound)
        if self.lower_bound != 0:
            gap = 100*(self.upper_bound - self.lower_bound)/self.upper_bound
            self.gap = min(gap, 100.00)
        elif self.lower_bound == self.upper_bound:
            self.gap = 0.00
        else:
            self.gap = 100.00

        # Add logging info to log file
        row = {"Stage": stage, "UB": round(self.upper_bound, 3), "LB": round(self.lower_bound, 3),
               "Gap": round(self.gap, 2), "Time": round(self.runtime.value, 2),
               "#Columns": len(self.column_pool.keys())}
        self.log.loc[len(self.log)] = row
        if self.log_path is not None:
            self.log.to_csv(self.log_path, index=False)

        # Log to console
        print(f"Stage: {stage} | UB: {self.upper_bound:.3f} | LB: {self.lower_bound:.3f} | "
              f"Gap: {self.gap:.2f} Time: {self.runtime.value:.2f} |  #Columns {len(self.column_pool.keys())}")

    def Propagate(self, bound=None):
        """
        Propagates the time windows of the activities for given or currently best known upper bound.

        Args:
            bound (float, optional): Bound on objective function value used for propagation.
        """
        cp = ConstraintProgram(instance=self.instance)
        cp.populate_model()
        effective_bound = self.upper_bound if bound is None else bound
        if effective_bound != src.Constants.INFINITY:
            cp.add_upper_bound_constraint(upper_bound=effective_bound)
        cp.model.set_parameters({'DefaultInferenceLevel': 'Extended'})
        sol = cp.model.propagate()
        for key, var in cp.x.items():
            domain = sol.get_value(var)
            if isinstance(domain.start, int) is False:
                self.instance.projects[key[0]].activities[key[1]].earliest_start = domain.start[0]
                self.instance.projects[key[0]].activities[key[1]].latest_start = domain.start[1]
            else:
                self.instance.projects[key[0]].activities[key[1]].earliest_start = domain.start
                self.instance.projects[key[0]].activities[key[1]].latest_start = domain.start

    def CP_OBBT(self):
        """
        Presolves the MRCMPSP instances via CP-based optimization-based bound tightening.
        """
        # Apply CP-OBBT to each project in parallel
        results = []
        for i, project in enumerate(self.instance.projects):
            result = self.worker_pool.apply_async(obbt_worker, args=(self.instance, i))
            results.append(result)
        [result.wait() for result in results]

        # Collect results and update the instance and column pool
        for result in results:
            project, solution_pool = result.get()
            self.instance.projects[project.index] = project
            self.add_column_to_pool(solution_pool=solution_pool, projects=[project], stage=STAGE_OBBT)

        # Compute trivial lower bound
        lb = sum(project.activities[-1].earliest_start - (project.release_date + project.critical_path_duration)
                 for i, project in enumerate(self.instance.projects))
        self.lower_bound = max(self.lower_bound, lb)

        print(f"Presolve (CP-OBBT) finished in {time.perf_counter() - self.start_time:.2f} secs "
              f"and improved the lower bound to {self.lower_bound:.2f}")

    def select_neighborhood(self, size, tabu_list):
        """
        Selects a neighborhood not in the tabu list yet.

        Args:
            size (int): Target size (i.e. number of projects) of neighborhood.
            tabu_list (int): Tabu list of forbidden neighborhoods.

        Returns:
            list of Int: Neighborhood.
        """
        # Repeatedly sample a random subset of projects of the target size until one not
        # already in the tabu list is found, growing the size after too many failed
        # attempts, until falling back to "all projects" if even that is exhausted.
        projects = [project.index for project in self.instance.projects]
        fails = 0
        neighborhood = []
        while neighborhood in tabu_list or neighborhood == []:
            fails += 1
            if fails > 100:
                size += 1
            if size == len(self.instance.projects):
                neighborhood.sort()
                if neighborhood in tabu_list:
                    return None
                else:
                    neighborhood = projects
                    break
            neighborhood = random.sample(population=projects, k=max(size, 1))
            neighborhood.sort()

        # Add to Tabu List
        tabu_list.append(neighborhood)

        return neighborhood

    def CP_LNS(self, time_limit):
        """
        Performs a CP-based large neighborhood search for a given time limit.

        Args:
            time_limit (float): Time limit in seconds.
        """

        lns_start_time = time.perf_counter()

        # Line 1 of pseudocode
        neighborhood_size = 0
        tabu_list = []

        # Line 2 of pseudocode
        # Solve CP to obtain initial solutions
        cp = ConstraintProgram(instance=self.instance)
        cp.populate_model()
        cp.solve(starting_heuristic=True, TimeLimit=src.Constants.ALPHA_LNS, OutputFlag=True)
        self.add_column_to_pool(solution_pool=cp.solution_pool, projects=self.instance.projects, stage=STAGE_LNS)

        # Update bounds and solution
        self.upper_bound = min(cp.objective_value, self.upper_bound)
        self.lower_bound = max(cp.objective_bound, self.lower_bound)
        self.solution = cp.solution
        if abs(self.upper_bound - self.lower_bound) < src.Constants.EPSILON:
            print(f"{self.instance.name}, {self.upper_bound}, {self.lower_bound}")
            return 0
        self.logging(stage=STAGE_LNS)

        # Line 3 of pseudocode
        # Propagate time windows based on upper bound
        self.Propagate()

        # Lines 4 to 9 of pseudocode
        iteration = 0
        results = []
        active = 0
        # Line 4 of pseudocode
        while neighborhood_size < len(self.instance.projects) - 1 and time.perf_counter() - lns_start_time < time_limit:
            if active < os.cpu_count():
                # Line 5 of pseudocode
                neighborhood = self.select_neighborhood(size=neighborhood_size, tabu_list=tabu_list)
                # Line 6 of pseudocode
                if neighborhood is not None:
                    result = self.worker_pool.apply_async(lns_worker, args=(self.instance, self.solution, neighborhood,
                                                                            self.queue, self.lock))
                    results.append(result)
                    active += 1
            if iteration > 0 and active == 0:
                break
            with self.lock:
                if self.queue.empty():
                    pass
                else:
                    while self.queue.empty() is False:
                        active -= 1
                        neighborhood, solution_pool = self.queue.get()
                        projects = [self.instance.projects[i] for i in neighborhood]
                        try:
                            # Line 7 of pseudocode
                            self.add_column_to_pool(solution_pool=solution_pool, projects=projects, stage=STAGE_LNS)
                        except Exception as e:
                            print(f"add_column_to_pool failed for neighborhood {neighborhood}: {e}")
                        for sol in solution_pool:
                            # Line 8 of pseudocode
                            if sol.objective_value < self.solution.objective_value:
                                # Line 9 of pseudocode
                                self.solution = sol
                                self.upper_bound = sol.objective_value
                                self.Propagate()
                                self.logging(stage=STAGE_LNS)
                                print(f"Iter: {iteration}, UB: {self.upper_bound:.2f}, Time: {self.runtime.value}")
                    iteration += 1

        self.worker_pool.terminate()
        self.worker_pool.join()

    def _make_pricer(self, index, model_type, lock, dual_queue, master_event, column_event, queue,
                      start_event, stop_event, iteration, deadline=None):
        """
        Builds a Pricer for a given project, sharing the synchronization primitives common to
        every pricer created within the same CP_IP_CG call.

        Args:
            index (int): Index of the project the pricing problem corresponds to.
            model_type (str): Model type 'CP' or 'IP'.
            lock (multiprocessing.Manger.Lock): Lock for thread safety during multiprocessing.
            dual_queue (multiprocessing.Manger.Queue): Queue for sending dual values between multiple processes.
            master_event (multiprocessing.Event): Event signaling resolving of master problem.
            column_event (multiprocessing.Event): Event signaling the discovery of new columns.
            queue (multiprocessing.Manger.Queue): Queue for communicating between multiple processes.
            start_event (multiprocessing.Event): Event signaling start of solving pricing problem.
            stop_event (multiprocessing.Event): Event signaling end of solving pricing problem.
            iteration (multiprocessing.Value): Shared iteration/solve count used by the solver callback.
            deadline (float, optional): Time stamp (perf_counter) by which the pricing problem must terminate.

        Returns:
            Pricer: The constructed pricer.
        """
        return Pricer(name=str(index), instance=self.instance, index=index, model_type=model_type,
                      lock=lock, queue=queue, dual_queue=dual_queue,
                      start_event=start_event, stop_event=stop_event, master_event=master_event,
                      column_event=column_event, iteration=iteration, deadline=deadline)

    def CP_IP_CG(self, time_limit=3600, **params):
        """
        Solves the linear relaxation of the master problem via column generation.

        Args:
            time_limit (float): Time limit in seconds.
        """

        # Initialize master problem
        master_problem = MasterProblem(instance=self.instance)
        master_problem.populate_model()
        for c, column in self.column_pool.items():
            try:
                master_problem.add_column(column=column)
            except Exception as e:
                print(f"add_column failed for column {c}: {e}")

        # Initialize pricing problems
        print("initialize pricer")
        manager = multiprocessing.Manager()
        lock = multiprocessing.Lock()
        dual_queue = manager.Queue()
        queue = manager.Queue()
        bounder_queue = manager.Queue()
        start_events = []
        stop_events = []
        master_event = multiprocessing.Event()
        column_event = multiprocessing.Event()
        shared_iteration = multiprocessing.Value("i", 0)
        shared_solve_count = multiprocessing.Value("i", 0)
        master_event.set()
        pricers = {}
        start = []
        start_iteration = []
        for i, project in enumerate(self.instance.projects):
            print(f"pricer {i}")
            start_event_cp = multiprocessing.Event()
            start_event_ip = multiprocessing.Event()
            start_events.append((start_event_cp, start_event_ip))
            stop_event_cp = multiprocessing.Event()
            stop_event_ip = multiprocessing.Event()
            stop_events.append((stop_event_cp, stop_event_ip))
            pricer_cp = self._make_pricer(index=i, model_type="CP", lock=lock, dual_queue=dual_queue,
                                          master_event=master_event, column_event=column_event,
                                          queue=queue, start_event=start_event_cp, stop_event=stop_event_cp,
                                          iteration=shared_iteration)
            pricer_ip = self._make_pricer(index=i, model_type="IP", lock=lock, dual_queue=dual_queue,
                                          master_event=master_event, column_event=column_event,
                                          queue=bounder_queue, start_event=start_event_ip, stop_event=stop_event_ip,
                                          iteration=shared_solve_count, deadline=self.start_time + time_limit)
            pricers[i] = [pricer_cp, pricer_ip]
            start.append(True)
            start_iteration.append(0)

        # Column generation
        column_count = len(self.column_pool)
        suboptimal = True
        for i, pricer in pricers.items():
            pricer[0].start()
            pricer[1].start()

        # Line 1 of pseudocode
        upper_bound_cg = self.upper_bound
        iteration = 0
        cp_phase_start = time.perf_counter()
        # Line 2 of pseudocode
        print(f"start column generation with time limit {time_limit}")
        while (upper_bound_cg if math.isinf(upper_bound_cg) else math.floor(upper_bound_cg)) \
                - (self.lower_bound - src.Constants.EPSILON) > src.Constants.EPSILON\
                and time.perf_counter()-self.start_time < time_limit\
                and time_limit - (time.perf_counter()-self.start_time) > src.Constants.ALPHA_CG:

            # Line 3 of pseudcode
            columns_added = False

            # Line 4 of pseudocode
            remaining_time = time_limit - (time.perf_counter()-self.start_time)
            master_problem.solve(TimeLimit=remaining_time)
            upper_bound_cg = master_problem.model.ObjVal
            if master_problem.model.Status == 3 or master_problem.model.Status == 9:
                break
            duals_i, duals_k_t = master_problem.retrieve_duals()
            with lock:
                while dual_queue.empty() is False:
                    dual_queue.get()
                dual_queue.put((duals_i, duals_k_t))

            # Line 5 of pseudocode
            for i, pricer in pricers.items():
                # Line 6 of pseudocode
                if start[i]:
                    #print(f"start CP pricing {i}")
                    start_events[i][0].set()
                    start[i] = False
                    start_iteration[i] = shared_iteration.value

            # Wait for pricing problems to terminate
            master_event.wait()
            with lock:
                master_event.clear()

            # Line 8 of pseudocode
            indices = []
            solutions = []
            with lock:
                while queue.empty() is False:
                    i, solution = queue.get()
                    indices.append(i)
                    solutions.append(solution)
                    columns_added = True
                    start[i] = True
            column_count = len(self.column_pool.keys())
            for key, sol in enumerate(solutions):
                self.add_column_to_pool(solution_pool=[sol], projects=[self.instance.projects[indices[key]]], stage=STAGE_CG_CP)
                start[indices[key]] = True  # Restart pricing problem after resolving master problem
            for c in range(column_count, len(self.column_pool.keys())):
                master_problem.add_column(self.column_pool[c])
                columns_added = True

            # Restart pricing problems that did not find a column
            if columns_added:
                for i, pricer in pricers.items():
                    if start[i] is False and stop_events[i][0].is_set():
                        if start_events[i][0].is_set() is False:
                            start[i] = True

            # Check if all pricing problems failed to find an improving column
            else:
                finished = True
                for i, pricer in pricers.items():
                    if stop_events[i][0].is_set() is False:  # or stop_events[i][1].is_set() is False:
                        finished = False
                    elif start_iteration[i] < shared_iteration.value:
                        finished = False
                        start[i] = True
                        print(
                            f"restart pricing problem {i} due to lag {shared_iteration.value}-{start_iteration[i]} ="
                            f" {shared_iteration.value - start_iteration[i]} ")
                        start_iteration[i] = shared_iteration.value
                if finished:
                    if queue.empty():
                        print("no improving column found")
                        break
            #else:
            #    for i, pricer in pricers.items():
            #        start[i] = True
            if columns_added:
                iteration += 1
                shared_iteration.value = iteration
                self.logging(stage=STAGE_CG_CP)
                print(f"Iter: {iteration} ({shared_iteration.value}) | UB: {upper_bound_cg:.3f} | LB:{self.lower_bound:.3f} | T"
                      f"ime: {time.perf_counter() - self.start_time:.2f}"
                      f"| #Col: {len(self.column_pool.keys())}")

        # Close parallel processes
        for i, pricer in pricers.items():
            pricer[0].terminate()
        for i, pricer in pricers.items():
            pricer[0].join()
        self.phase_durations["CG-CP"] = time.perf_counter() - cp_phase_start

        #while math.floor(upper_bound_cg) - (self.lower_bound-src.Constants.EPSILON) > src.Constants.EPSILON\
        #    and \
        print(f"Iter: {iteration} ({shared_iteration.value}) | UB: {upper_bound_cg:.3f} | LB:{self.lower_bound:.3f} | T"
              f"ime: {time.perf_counter() - self.start_time:.2f}"
              f"| #Col: {len(self.column_pool.keys())}")
        remaining_time = time_limit - (time.perf_counter() - self.start_time)
        master_problem.solve(TimeLimit=remaining_time)
        upper_bound_cg = master_problem.model.ObjVal
        self.Propagate(math.ceil(upper_bound_cg))

        ip_phase_start = time.perf_counter()
        while math.floor(upper_bound_cg) - (self.lower_bound - src.Constants.EPSILON) > src.Constants.EPSILON\
            and time.perf_counter()-self.start_time < time_limit:

            # Line 10 of pseudocode
            shared_solve_count.value = 0
            remaining_time = time_limit - (time.perf_counter() - self.start_time)
            master_problem.solve(TimeLimit=remaining_time)
            upper_bound_cg = master_problem.model.ObjVal
            if master_problem.model.Status == 3 or master_problem.model.Status == 9:
                break

            duals_i, duals_k_t = master_problem.retrieve_duals()
            with lock:
                while dual_queue.empty() is False:
                    dual_queue.get()
                dual_queue.put((duals_i, duals_k_t))

            # Line 11 of pseudocode
            for i, pricer in pricers.items():
                start_events[i][1].set()
                start[i] = False
                last_upper_bound = upper_bound_cg

            for event in stop_events:
                event[1].wait()

            # Line 12 of pseudocode
            columns_added = False
            indices = []
            solutions = []
            neg_reduced_costs = [0 for p in self.instance.projects]
            with lock:
                while bounder_queue.empty() is False:
                    reduced_costs, i, solution = bounder_queue.get()
                    neg_reduced_costs[i] = reduced_costs
                    if solution is not None:
                        indices.append(i)
                        solutions.append(solution)
            lower_bound = last_upper_bound + sum(neg_reduced_costs)
            print(f"lower bound {lower_bound} = {last_upper_bound} + {sum(neg_reduced_costs)}")

            self.logging(stage=STAGE_CG_IP)
            if self.lower_bound < lower_bound:
                self.lower_bound = lower_bound
            with lock:
                while queue.empty() is False:
                    i, solution = queue.get()
                    indices.append(i)
                    solutions.append(solution)
                    columns_added = True
            column_count = len(self.column_pool.keys())
            for key, sol in enumerate(solutions):
                self.add_column_to_pool(solution_pool=[sol], projects=[self.instance.projects[indices[key]]], stage=STAGE_CG_IP)
                column_found = True
                start[indices[key]] = True  # Restart pricing problem after resolving master problem
            for c in range(column_count, len(self.column_pool.keys())):
                master_problem.add_column(self.column_pool[c])

            iteration += 1
            print(f"Iter: {iteration} | UB: {upper_bound_cg:.3f} | LB:{self.lower_bound:.3f} | T"
                  f"ime: {time.perf_counter() - self.start_time:.2f}"
                  f"| #Col: {len(self.column_pool.keys())}")

        # Close parallel processes
        for i, pricer in pricers.items():
            pricer[1].terminate()
        for i, pricer in pricers.items():
            pricer[1].join()
        self.phase_durations["CG-IP"] = time.perf_counter() - ip_phase_start

    def build_summary(self):
        """
        Builds the end-of-run summary: time spent, and unique/total columns generated, per phase.

        Returns:
            dict: Summary containing, per phase, the time spent and unique/total columns generated, plus the
                total runtime, final bounds/gap, and total (unique) columns generated overall.
        """
        summary = {
            phase: {
                "time_seconds": round(self.phase_durations.get(phase, 0.0), 2),
                "unique_columns": self.unique_columns_per_stage.get(phase, 0),
                "total_columns": self.total_columns_per_stage.get(phase, 0),
            }
            for phase in PHASES
        }
        summary["total_time_seconds"] = round(time.perf_counter() - self.run_start_time, 2)
        summary["final_lower_bound"] = self.lower_bound
        summary["final_upper_bound"] = self.upper_bound
        summary["final_gap"] = self.gap
        summary["total_unique_columns"] = len(self.seen_column_signatures)
        summary["total_columns"] = len(self.column_pool)
        return summary
