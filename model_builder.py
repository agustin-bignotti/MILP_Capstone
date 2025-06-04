# model_builder.py
from gurobipy import Model, GRB, quicksum

def build_model(params):

    """
    Construye y retorna el modelo Gurobi para la calendarización de motores.
    Recibe en `params` todos los datos generados por `data_loader.py`:
      - P_WB, I_WB, I_extra, T, c, C, y0, LeaseCost, BuyCost, d, S0, M_max, M.
    """

    # ─── Extracción de parámetros de params ───────────────────────────────────────
    P_WB = params['P_WB']         # Lista de IDs de aviones
    I_WB = params['I_WB']         # Lista de IDs de todos los motores (propios + extras)
    I_extra = params['I_extra']   # IDs de los motores extra que se pueden comprar
    T = params['T']               # Horizonte de semanas (1…54)
    c = params['c']               # Diccionario: c[i] = ciclos/semana para motor i (basado en operación)
    C = params['C']               # Diccionario: C[i] = umbral ciclo máximo para motor i
    y0 = params['y0']             # Diccionario: y0[i] = ciclos iniciales del motor i en t=0
    LeaseCost = params['LeaseCost']
    BuyCost = params['BuyCost']
    d = params['d']               # Duración del mantenimiento (en semanas)
    S0 = params['S0']             # Stock inicial de repuestos en t=1
    M_max = params['M_max']       # Máximo motores que pueden entrar a mant. por semana
    M = params['M']               # Ciclo máximo estricto para motores propios (no extras)
    n_aviones = len(P_WB)         # Cantidad de motores “propios” (IDs 1…n_aviones)
    bigM      = M                 # BigM, ya calculado en data_loader como max(C.values())


    # ─── (3) INSTANCIAR MODELO Y VARIABLES ────────────────────────────────────────
    model = Model("WB_Maintenance")
    model.Params.OutputFlag = 1   # 1 para ver salida, 0 para silenciar

    # 3.1. Variables de asignación y stock
    # a[i,p,t] = 1 si el motor i está instalado en el avión p en la semana t
    a = model.addVars(I_WB, P_WB, T, vtype=GRB.BINARY, name="a")
    # s[i,t] = 1 si el motor i está en stock al inicio de la semana t
    s = model.addVars(I_WB, T, vtype=GRB.BINARY, name="s")

    # 3.2. Variables de mantenimiento
    # m[i,t] = 1 si el motor i inicia mantenimiento en la semana t
    m = model.addVars(I_WB, T, vtype=GRB.BINARY, name="m")
    # r[i,t] = 1 si el motor i está en mantenimiento en la semana t
    r = model.addVars(I_WB, T, vtype=GRB.BINARY, name="r")

    # 3.3. Variables de ciclos e inventario agregado
    # y[i,t] = ciclos acumulados por el motor i al cierre de la semana t
    y = model.addVars(I_WB, T, vtype=GRB.CONTINUOUS, lb=0, name="y")
    # S[t] = inventario agregado de repuestos al inicio de la semana t
    S = model.addVars(T, vtype=GRB.CONTINUOUS, lb=0, name="S")

    # 3.4. Variables de cobertura con arrendo o compra
    # ell[p,t] = 1 si el avión p opera con motor arrendado en la semana t
    ell = model.addVars(P_WB, T, vtype=GRB.BINARY, name="ell")

    # 3.5. Variable binaria: buy_extra[i,t] = 1 si compramos el motor extra i en la semana t
    buy_extra = model.addVars(I_extra, T, vtype=GRB.BINARY, name="buy_extra")

    # 3.6. Variables auxiliares para acumulación de compras de motores extra
    # buy_cum[i,t] = compras acumuladas del motor extra i hasta la semana t
    buy_cum = {}
    for i in I_extra:
        for t in T:
            buy_cum[i, t] = quicksum(buy_extra[i, tau] for tau in range(1, t+1))


    # ─── (4) RESTRICCIONES ──────────────────────────────────────────────────────────

    # 4.0 Asignación inicial en t=1
    for i in I_WB:
        if i <= n_aviones:
            # Si i es motor propio (1…n_aviones), obligo a que en t=1 esté en avión i
            model.addConstr(a[i, i, 1] == 1, name=f"init_assign_{i}_{i}")
            model.addConstr(r[i, 1] == 0, name=f"init_no_maint_{i}")
            model.addConstr(s[i, 1] == 0, name=f"init_no_stock_{i}")
            for p in P_WB:
                if p != i:
                    model.addConstr(a[i, p, 1] == 0, name=f"init_noassign_{i}_{p}")
        else:
            # Si i es motor extra (i > n_aviones), entonces en t=1:
            for p in P_WB:
                model.addConstr(a[i, p, 1] == 0, name=f"extra_noassign_{i}_{p}")
            model.addConstr(r[i, 1] == 0, name=f"extra_no_maint_{i}")
            model.addConstr(s[i, 1] == 0, name=f"extra_no_stock_{i}")

    # 4.1 Estados de cada motor en cada semana
    for i in I_WB:
        for t in T:
            if i in I_extra:
                # Para motores extras: hasta que no lo compro sum(a + r + s) = 0; luego = 1
                model.addConstr(
                    quicksum(a[i, p, t] for p in P_WB) + r[i, t] + s[i, t]
                    == buy_cum[i, t],
                    name=f"exclusive_extra_{i}_{t}"
                )
            else:
                # Para motores propios: siempre en exactamente un estado (asignado, en mantención o en stock)
                model.addConstr(
                    quicksum(a[i, p, t] for p in P_WB) + r[i, t] + s[i, t] == 1,
                    name=f"exclusive_init_{i}_{t}"
                )

    # 4.2 Cobertura: cada avión p en t usa o bien un motor (propio o extra) o bien arrienda
    for p in P_WB:
        for t in T:
            model.addConstr(
                quicksum(a[i, p, t] for i in I_WB) + ell[p, t] == 1,
                name=f"coverage_{p}_{t}"
            )

    # 4.3 Duración del mantenimiento: si m[i,t'] = 1 inicié mantención, entonces r[i,t] = 1 para t' ≤ t ≤ t'+d-1
    for i in I_WB:
        for t in T:
            model.addConstr(
                r[i, t] == quicksum(
                    m[i, tau] for tau in range(max(1, t-d+1), t+1)
                ),
                name=f"maint_duration_{i}_{t}"
            )

    # 4.4 Acumulación de ciclos con reset cuando termina mantención (versión simplificada)
    for i in I_WB:
        # Semana 1: ciclos iniciales + los que gana si está asignado
        model.addConstr(
            y[i, 1] == y0[i] + quicksum(c[p] * a[i, p, 1] for p in P_WB),
            name=f"init_cycles_{i}"
        )
        # Semanas t = 2…última
        for t in T[1:]:
            expr = quicksum(c[p] * a[i, p, t] for p in P_WB)
            if t <= d:
                # Para t ≤ d no puede haber terminado ninguna mantención previa
                model.addConstr(
                    y[i, t] == y[i, t-1] + expr,
                    name=f"cycles_accum_{i}_{t}"
                )
            else:
                # Para t > d, chequeamos si m[i,t-d] = 1 (termina mantención hoy)
                model.addConstr(
                    y[i, t] == (1 - m[i, t-d]) * (y[i, t-1] + expr)
                                + m[i, t-d] * expr,
                    name=f"cycles_reset_exact_{i}_{t}"
                )


    # 4.5 Límite estricto de ciclos tras mantención
    for i in I_WB:
        for t in T:
            model.addConstr(
                y[i, t] <= C[i] + (max(C.values()) if i in I_extra else 0) * r[i, t],
                name=f"cycle_limit_strict_{i}_{t}"
            )

    # 4.6 Capacidad: a lo sumo M_max inicios de mantención cada semana
    for t in T:
        model.addConstr(
            quicksum(m[i, t] for i in I_WB) <= M_max,
            name=f"capacity_{t}"
        )

    # 4.7 Flujo de inventario de repuestos (stock)
    # Semana 1: stock inicial S[1] = S0 + compras en t=1
    model.addConstr(
        S[1] == S0 + quicksum(buy_extra[i, 1] for i in I_extra),
        name="stock_init"
    )
    # Semanas t=2…: stock[t] = stock[t-1] + compras[t] + retornos mant[t]
    for t in T[1:]:
        model.addConstr(
            S[t] == S[t-1]
                      + quicksum(buy_extra[i, t] for i in I_extra)
                      + quicksum(m[i, t-d] for i in I_WB if t-d > 0),
            name=f"stock_flow_{t}"
        )

    # 4.8: Continuidad de asignación: si motor i estaba en avión p en t-1 y no entró a mantención en t, entonces en t debe seguir ahí
    for i in I_WB:
        for p in P_WB:
            for t in T[1:]:
                model.addConstr(
                    a[i, p, t] >= a[i, p, t-1] - m[i, t],
                    name=f"continuity_{i}_{p}_{t}"
                )

    # 4.9 Solo puede estar en stock si ya se compró (motores extra)
    for i in I_extra:
        for t in T:
            model.addConstr(
                s[i, t] <= buy_cum[i, t],
                name=f"no_stock_before_buy_{i}_{t}"
            )

    # 4.10 Solo asignar motor extra si ya está comprado
    for i in I_extra:
        for p in P_WB:
            for t in T:
                model.addConstr(
                    a[i, p, t] <= buy_cum[i, t],
                    name=f"assign_only_if_bought_{i}_{p}_{t}"
                )

    # 4.11 Si compro motor extra i en la semana t, forzosamente se debe usar en t
    for i in I_extra:
        for t in T:
            model.addConstr(
                quicksum(a[i, p, t] for p in P_WB) >= buy_extra[i, t],
                name=f"use_bought_engine_{i}_{t}"
            )

    # 4.12 Cada motor extra solo puede comprarse una vez
    for i in I_extra:
        model.addConstr(
            quicksum(buy_extra[i, t] for t in T) <= 1,
            name=f"max_one_purchase_extra_{i}"
        )

    # 4.13 HEURÍSTICA en semanas impares (t = 3,5,7,…)
    # (= reproducir exactamente tu bloque original, T[1:] arranca en t=2)
    for t in T[1:]:
        if t % 2 != 0:
            # 1) No iniciar mantención
            for i in I_WB:
                model.addConstr(m[i, t] == 0, name=f"no_maint_odd_{i}_{t}")
            # 2) No comprar motores extra
            for i in I_extra:
                model.addConstr(buy_extra[i, t] == 0, name=f"no_buy_odd_{i}_{t}")
            # 3) No cambiar arrendamiento: ell[p,t] == ell[p,t-1]
            for p in P_WB:
                model.addConstr(ell[p, t] == ell[p, t-1], name=f"lease_const_odd_{p}_{t}")
            # 4) No cambiar asignación: a[i,p,t] == a[i,p,t-1]
            for i in I_WB:
                for p in P_WB:
                    model.addConstr(a[i, p, t] == a[i, p, t-1], name=f"assign_const_odd_{i}_{p}_{t}")
            # 5) No cambiar stock: s[i,t] == s[i,t-1]
            for i in I_WB:
                model.addConstr(s[i, t] == s[i, t-1], name=f"stock_const_odd_{i}_{t}")

    # 4.14 Ciclo máximo estricto en todas las semanas (para implementar heurística en pares)
    for i in I_WB:
        for t in T:
            model.addConstr(
                y[i, t] <= C[i],
                name=f"cycle_limit_strict_no_over_{i}_{t}"
            )

    # ─── (5) FUNCIÓN OBJETIVO ────────────────────────────────────────────────────────
    model.setObjective(
        # 5.1 Costo total = arrendos + compras
        quicksum(LeaseCost * ell[p, t] for p in P_WB for t in T)
        + quicksum(BuyCost * buy_extra[i, t] for i in I_extra for t in T),
        GRB.MINIMIZE
    )

    # Guardar en params las variables que después usarán heuristics.py y report_writer.py
    params['model_components'] = {
        'a': a,
        's': s,
        'm': m,
        'r': r,
        'y': y,
        'S': S,
        'ell': ell,
        'buy_extra': buy_extra
    }

    return model
