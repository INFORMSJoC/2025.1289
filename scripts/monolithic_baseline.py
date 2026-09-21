# Internal Dependencies
from src.Instance import Instance
from src.ConstraintProgram import ConstraintProgram
from src.IntegerProgram import IntegerProgram
from pathlib import Path
import time


if __name__ == '__main__':
    time_limit = 3600

    # Iterates over all instances and solves them independently via CP and IP, each
    # against the full time_limit budget (which also covers model-population time).
    dir_path = Path(__file__).resolve().parent.parent / "data" / "MISTA"
    for file in sorted(dir_path.glob("*.json")):
        path = file.with_suffix("")
        instance = Instance.from_json(path)
        print(instance.name)

        # Solve instance via CP
        cp_start_time = time.perf_counter()
        try:
            cp = ConstraintProgram(instance=instance)
            cp.populate_model()
            cp.solve(TimeLimit=time_limit - (time.perf_counter() - cp_start_time), OutputFlag=True)
            print(f"CP objective: {cp.objective_value}, runtime: {cp.runtime:.2f}s")
        except Exception as e:
            print(f"{instance.name} CP failed: {e}")

        # Solve instance via IP
        ip_start_time = time.perf_counter()
        try:
            ip = IntegerProgram(instance=instance)
            ip.populate_model()
            ip.solve(TimeLimit=time_limit - (time.perf_counter() - ip_start_time), OutputFlag=True)
            print(f"IP objective: {ip.objective_value}, runtime: {ip.runtime:.2f}s")
        except Exception as e:
            print(f"{instance.name} IP failed: {e}")