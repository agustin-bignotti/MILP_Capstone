# main.py

import time
import os
from datetime import datetime

from data_loader import load_data
from model_builder import build_model
from heuristics import warm_start
from report_writer import write_reports


def get_next_run_id():
    """
    Lee/modifica processed_data/last_run_id.txt para obtener un run_id incremental.
    Si no existe processed_data/ o last_run_id.txt, los crea.
    """
    counter_file = "processed_data/last_run_id.txt"
    if not os.path.isdir("processed_data"):
        os.makedirs("processed_data")

    if os.path.isfile(counter_file):
        with open(counter_file, 'r') as f:
            prev = int(f.read().strip())
    else:
        prev = 0

    new_id = prev + 1
    with open(counter_file, 'w') as f:
        f.write(str(new_id))

    return f"run{new_id:03d}"


def main():
    # Registrar hora de inicio
    start_time = time.time()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_id = get_next_run_id()

    # Carga de datos
    params = load_data('Datos')
    model = build_model(params)

    # Warm start heuristic
    warm_start(model, params)

    # Optimización
    model.optimize()

    # Al terminar, medir duración
    end_time = time.time()
    runtime_s = end_time - start_time

    # Escribir reportes si hay solución
    if model.SolCount > 0:
        print(f"Costo (mejor incumbent) : {model.objVal}")
        write_reports(model, params, timestamp, runtime_s, run_id)
    else:
        print("No se encontró solución factible. Estado:", model.status)


if __name__ == "__main__":
    main()
