# report_writer.py

import os
import pandas as pd


def write_reports(model, params, timestamp, runtime_s, run_id):
    """
    Genera dos reportes en CSV dentro de processed_data/reports y actualiza run_log.csv en processed_data/.

    Parámetros:
      - model: instancia de Gurobi ya optimizada.
      - params: diccionario con variables y datos.
      - timestamp: string "YYYY-MM-DD_HH-MM-SS".
      - runtime_s: duración de la corrida en segundos (float).
      - run_id: identificador único de corrida (p.ej. "run001").
    """

    # ── 0) Verificar/crear carpeta de salida principal ─────────────────────────────
    base_folder = "processed_data"
    if not os.path.isdir(base_folder):
        os.makedirs(base_folder)

    # ── 1) Verificar/crear subcarpeta de reportes ─────────────────────────────────
    reports_folder = os.path.join(base_folder, "reports")
    if not os.path.isdir(reports_folder):
        os.makedirs(reports_folder)

    # ── 2) Extraer variables y datos de params ─────────────────────────────────────
    comps      = params['model_components']
    a          = comps['a']
    y          = comps['y']
    ell        = comps['ell']
    buy_extra  = comps['buy_extra']
    r          = comps['r']
    s          = comps['s']
    P_WB       = params['P_WB']
    I_WB       = params['I_WB']
    I_extra    = params['I_extra']
    T          = params['T']
    C          = params['C']
    id2mat     = params.get('id2mat', {})
    LeaseCost  = params['LeaseCost']
    BuyCost    = params['BuyCost']

    # ── 3) Calcular metadatos básicos ───────────────────────────────────────────────
    horizonte    = len(T)
    fleet_size   = len(P_WB)
    num_extra    = len(I_extra)
    total_cost   = model.objVal if model.SolCount > 0 else None
    runtime_str  = f"{int(runtime_s)}s"  # solo segundos, por simplicidad

    # ── 4) Construir nombres de archivo con run_id al inicio ───────────────────────
    base_name_plane  = f"{run_id}_plane_weekly_status_T{horizonte}.csv"
    base_name_weekly = f"{run_id}_weekly_report_T{horizonte}.csv"
    file_plane       = os.path.join(reports_folder, base_name_plane)
    file_weekly      = os.path.join(reports_folder, base_name_weekly)

    # ── 5) Crear CSV agrupado por avión ────────────────────────────────────────────
    records_plane = []
    lease_count   = {p: 0 for p in P_WB}

    for t in T:
        for p in P_WB:
            motor = None
            # Si i ≤ n_aviones, revisa solo i=p
            if (p, p, t) in a and a[(p, p, t)].X > 0.5:
                motor = p
            else:
                # revisa motores extra
                for i in I_extra:
                    if a[(i, p, t)].X > 0.5:
                        motor = i
                        break

            cycles = y[motor, t].X if motor is not None else 0
            # Redondear ciclos acumulados a dos decimales
            cycles = round(cycles, 2)
            threshold = C[p]

            if ell[p, t].X > 0.5:
                lease_count[p] += 1
                lease_tag = f"lease_{lease_count[p]}"
            else:
                lease_tag = ""

            if motor in I_extra and buy_extra[motor, t].X > 0.5:
                bought = "buy"
            else:
                bought = ""

            over = int(cycles > threshold)

            records_plane.append({
                'Semana':            t,
                'Avion_ID':          p,
                'Motor_asignado':    id2mat.get(motor, None) if motor else None,
                'Ciclos_acumulados': cycles,
                'Umbral_maximo':     threshold,
                'Leased':            lease_tag,
                'Bought':            bought,
                'OverThreshold':     over
            })

    df_plane = pd.DataFrame(records_plane)
    df_plane.to_csv(file_plane, index=False)
    print(f"-> {file_plane} ({len(df_plane)} filas)")

    # ── 6) Crear CSV de reporte semanal ─────────────────────────────────────────────
    records_weekly = []
    cum_cost = 0.0

    for t in T:
        cum_cost += (
            sum(LeaseCost * ell[p, t].X for p in P_WB)
            + sum(BuyCost * buy_extra[i, t].X for i in I_extra)
        )

        n_mant  = sum(int(r[i, t].X > 0.5) for i in I_WB)
        n_lease = sum(int(ell[p, t].X > 0.5) for p in P_WB)
        n_buy   = sum(int(buy_extra[i, t].X > 0.5) for i in I_extra)
        n_over  = sum(int(y[i, t].X > C[i]) for i in I_WB)
        n_stock = sum(int(s[i, t].X > 0.5) for i in I_WB)

        records_weekly.append({
            'Semana':                   t,
            'Num_Aviones':              fleet_size,
            'Motores_en_mantenimiento': n_mant,
            'Motores_arrendados':       n_lease,
            'Motores_comprados':        n_buy,
            'Motores_en_stock':         n_stock,
            'Motores_sobreciclo':       n_over,
            'Costo_acumulado':          cum_cost
        })

    df_weekly_report = pd.DataFrame(records_weekly)
    df_weekly_report.to_csv(file_weekly, index=False)
    print(f"-> {file_weekly} ({len(df_weekly_report)} filas)")

    # ── 7) Registrar metadatos en run_log.csv ──────────────────────────────────────
    log_file = os.path.join(base_folder, "run_log.csv")
    log_exists = os.path.isfile(log_file)

    log_entry = {
        'run_id':       run_id,
        'timestamp':    timestamp,
        'horizonte':    horizonte,
        'fleet_size':   fleet_size,
        'LeaseCost':    LeaseCost,
        'BuyCost':      BuyCost,
        'runtime_s':    round(runtime_s, 2),
        'total_cost':   total_cost,
        'num_extra':    num_extra,
        'file_plane':   os.path.join("reports", base_name_plane),
        'file_weekly':  os.path.join("reports", base_name_weekly),
        'notes':        ""  # campo vacío para completar manualmente
    }

    df_log = pd.DataFrame([log_entry])

    if not log_exists:
        df_log.to_csv(log_file, index=False)
    else:
        df_log.to_csv(log_file, mode='a', header=False, index=False)

    print(f"-> Metadatos guardados en {log_file}")
