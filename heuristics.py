# heuristics.py

def warm_start(model, params):
    """
    Aplica una heurística voraz (greedy) para asignar motores propios antes de optimizar.
    Recibe:
      - model: el objeto Gurobi Model ya construido.
      - params: diccionario con datos (y0, c, C, P_WB, T) y con las variables en params['model_components'].
    Deja en `.Start` de cada variable la solución inicial para que Gurobi la use como warm‐start.
    """

    # 1) Extraer directamente las variables binarias del modelo
    a         = params['model_components']['a']
    ell       = params['model_components']['ell']
    buy_extra = params['model_components']['buy_extra']

    # 2) Datos para la heurística
    cycles_greedy = params['y0'].copy()  # copia de ciclos iniciales para simular rotación
    P_WB          = params['P_WB']
    c             = params['c']
    C             = params['C']
    T             = params['T']

    # 3) Resetear valores Start de todas las variables binarias
    for var in list(a.values()) + list(ell.values()) + list(buy_extra.values()):
        var.Start = 0

    # 4) Heurística voraz: asignar motores propios si tienen capacidad de ciclos
    for t in T:
        for p in P_WB:
            elegido = None
            # Recorremos motores propios (IDs 1…n_aviones)
            for i in range(1, len(P_WB) + 1):
                if cycles_greedy[i] + c[p] <= C[i]:
                    elegido = i
                    break

            if elegido:
                # Asignar motor propio i al avión p en semana t
                a[elegido, p, t].Start = 1
                cycles_greedy[elegido] += c[p]
            else:
                # Si no hay motor propio con capacidad, arrendamos
                ell[p, t].Start = 1
