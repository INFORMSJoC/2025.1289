# Internal Dependencies
from src.Instance import Instance
from src.Hybrid_Solver import Hybrid_Solver
from pathlib import Path
import time


if __name__ == '__main__':
    time_limit = 3600

    # Iterates over all instances and solves them via CP-DWD with the CP-OBBT presolve phase disabled
    dir_path = Path(__file__).resolve().parent.parent / "data" / "MISTA"
    for file in sorted(dir_path.glob("*.json")):
        try:
            path = file.with_suffix("")
            instance = Instance.from_json(path)
            print(instance.name)

            # Solve instance via CP-DWD, skipping CP-OBBT
            hsf_p = Hybrid_Solver(instance=instance)
            hsf_p.CP_DWD(TimeLimit=time_limit, DisableOBBT=True)

        except Exception as e:
            print(f"{instance.name} failed: {e}")
