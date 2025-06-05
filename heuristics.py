# heuristics.py

def warm_start(model, params):
    """
    Aplica una heurística voraz (greedy) para asignar motores propios antes de optimizar.
    Recibe:
      - model: el objeto Gurobi Model ya construido.
      - params: diccionario con datos y las variables en params['model_components'].
    Deja en `.Start` de cada variable la solución inicial para que Gurobi la use como warm‐start.
    """

    # 1) Extraer las variables binarias del modelo
    a         = params['model_components']['a']
    ell       = params['model_components']['ell']
    buy_extra = params['model_components']['buy_extra']

    # 2) Datos para la heurística
    cycles_greedy = params['y0'].copy()
    P_WB          = params['P_WB']
    I_WB          = params['I_WB']
    I_extra       = params['I_extra']
    c             = params['c']
    C             = params['C']
    T             = params['T']

    # 3) Resetear todos los valores Start de variables binarias
    for var in list(a.values()) + list(ell.values()) + list(buy_extra.values()):
        var.Start = 0

    # 4) Heurística voraz: para cada semana t, cada avión p
    for t in T:
        for p in P_WB:
            # Intentar usar el motor propio p
            if cycles_greedy[p] + c[p] <= C[p]:
                # Existe a[(p, p, t)] en el diccionario
                a[(p, p, t)].Start = 1
                cycles_greedy[p] += c[p]
            else:
                # No cabe el propio; arrendar
                ell[p, t].Start = 1
