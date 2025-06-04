
# Explicación detallada de `model_builder.py`

A continuación encontrarás una explicación paso a paso de tu archivo `model_builder.py`. He dividido la explicación en bloques claros: los parámetros que recibe la función, las variables que se crean, las restricciones principales, la función objetivo y cómo se almacenan las variables para su uso posterior.

---

## 1. Código completo de `model_builder.py`

```python
from gurobipy import Model, GRB, quicksum

def build_model(params):
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
    M_max = params['M_max']       # Máximo motores que pueden entrar a mantención por semana

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

    # ─── (4) RESTRICCIONES ──────────────────────────────────────────────────────────

    # 4.0 Asignación inicial en t=1
    for i in I_WB:
        if i <= params['n_aviones']:
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
                    == quicksum(buy_extra[i, τ] for τ in range(1, t+1)),
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

    # 4.4 Acumulación de ciclos con reset cuando termina mantención
    for i in I_WB:
        # Semana 1
        model.addConstr(
            y[i, 1] == y0[i] + quicksum(c[p] * a[i, p, 1] for p in P_WB),
            name=f"init_cycles_{i}"
        )
        # Semanas t = 2…última
        for t in T[1:]:
            expr = quicksum(c[p] * a[i, p, t] for p in P_WB)
            if t - d >= 1:
                # Si hubo mantención en t-d, reinicia ciclos
                model.addConstr(
                    y[i, t] == (1 - m[i, t-d]) * (y[i, t-1] + expr) + m[i, t-d] * expr,
                    name=f"cycles_reset_exact_{i}_{t}"
                )
            else:
                model.addConstr(
                    y[i, t] == y[i, t-1] + expr,
                    name=f"cycles_accum_{i}_{t}"
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
                s[i, t] <= quicksum(buy_extra[i, τ] for τ in range(1, t+1)),
                name=f"no_stock_before_buy_{i}_{t}"
            )

    # 4.10 Solo asignar motor extra si ya está comprado
    for i in I_extra:
        for p in P_WB:
            for t in T:
                model.addConstr(
                    a[i, p, t] <= quicksum(buy_extra[i, tau] for tau in range(1, t+1)),
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
```

---

## 2. Explicación paso a paso

Voy a dividir la explicación en los siguientes bloques:

1. Parámetros que recibe la función.
2. Variables que se crean.
3. Restricciones principales (4.0 a 4.14).
4. Función objetivo.
5. Almacenamiento en `params['model_components']`.

### 2.1. Parámetros que recibe `build_model(params)`

- `params` es el diccionario que devolviste desde `data_loader.py`. Contiene:
  - Listas:  
    - `P_WB`: IDs de los aviones (por ejemplo `[1, 2, 3, …]`).  
    - `I_WB`: IDs de todos los motores (propios + extras).  
    - `I_extra`: IDs de los motores que podemos comprar.  
    - `T`: horizonte de semanas, p. ej. `list(range(1, 55))`.  
  - Diccionarios:  
    - `c[i]`: ciclos por semana del motor i.  
    - `C[i]`: umbral de ciclos máximos (threshold) para i.  
    - `y0[i]`: ciclos que ya lleva acumulados i antes de semana 1.  
  - Parámetros económicos: `LeaseCost`, `BuyCost`.  
  - Constantes:  
    - `d`: duración de un mantenimiento (en semanas).  
    - `S0`: stock de repuestos al inicio (semana 1).  
    - `M_max`: cuántos motores pueden entrar a mantención cada semana.  

Cuando dentro del código ves `P_WB = params['P_WB']`, es simplemente “copiar” esa lista para poder usarla localmente.

### 2.2. Variables

Definimos 8 grupos de variables:

1. **`a[i,p,t]` (binaria)**  
   - Significado: el motor `i` está asignado al avión `p` en la semana `t`.  
   - Dominio: i ∈ I_WB, p ∈ P_WB, t ∈ T.   
   - Sintaxis: `a = model.addVars(I_WB, P_WB, T, vtype=GRB.BINARY, name="a")`.  

2. **`s[i,t]` (binaria)**  
   - Significado: el motor `i` está en stock al inicio de la semana `t`.  
   - Dominio: i ∈ I_WB, t ∈ T.  
   - Sintaxis: `s = model.addVars(I_WB, T, vtype=GRB.BINARY, name="s")`.  

3. **`m[i,t]` (binaria)**  
   - Significado: el motor `i` inicia mantenimiento en la semana `t`.  
   - Dominio: i ∈ I_WB, t ∈ T.  
   - Sintaxis: `m = model.addVars(I_WB, T, vtype=GRB.BINARY, name="m")`.  

4. **`r[i,t]` (binaria)**  
   - Significado: el motor `i` está en mantenimiento en la semana `t`.  
   - Se define para vincularlo con `m[i,τ]` de semanas anteriores y saber cuándo está “dentro” del período de mantenimiento.  
   - Dominio: i ∈ I_WB, t ∈ T.  
   - Sintaxis: `r = model.addVars(I_WB, T, vtype=GRB.BINARY, name="r")`.  

5. **`y[i,t]` (continua)**  
   - Significado: ciclos acumulados por el motor `i` al cierre de la semana `t`.  
   - Dominio: i ∈ I_WB, t ∈ T.  
   - Restricción: siempre ≥ 0 (`lb=0`).  
   - Sintaxis: `y = model.addVars(I_WB, T, vtype=GRB.CONTINUOUS, lb=0, name="y")`.  

6. **`S[t]` (continua)**  
   - Significado: inventario total de motores en stock en la semana `t`.  
   - Dominio: t ∈ T, con límite inferior 0 (`lb=0`).  
   - Sintaxis: `S = model.addVars(T, vtype=GRB.CONTINUOUS, lb=0, name="S")`.  

7. **`ell[p,t]` (binaria)**  
   - Significado: el avión `p` en la semana `t` está operando con un motor arrendado (lease).  
   - Dominio: p ∈ P_WB, t ∈ T.  
   - Sintaxis: `ell = model.addVars(P_WB, T, vtype=GRB.BINARY, name="ell")`.  

8. **`buy_extra[i,t]` (binaria)**  
   - Significado: compramos el motor extra `i` en la semana `t`.  
   - Dominio: i ∈ I_extra, t ∈ T.  
   - Sintaxis: `buy_extra = model.addVars(I_extra, T, vtype=GRB.BINARY, name="buy_extra")`.  

**¿Por qué tantas variables?**  
- Necesitamos variables de asignación (`a`) para saber “qué motor está en qué avión cada semana”.  
- Necesitamos variables de stock (`s`) para no confundir un motor extra que compré pero aún no asigno.  
- Variable `m` y `r` se usan para modelar la duración del mantenimiento (por eso las dos).  
- `y[i,t]` lleva el conteo de ciclos semanales que suma el motor cada vez que vuela en un avión.  
- `S[t]` lleva la “suma total” de motores de repuesto en stock cada semana.  
- `ell[p,t]` me permite rentar motores para no paralizar un avión si todos sus motores propios están en riesgo de sobreciclo.  
- `buy_extra[i,t]` controla la compra de motores nuevos.  

Hasta aquí, **¿todo claro respecto a las variables y sus dominios?**  

---

### 2.3. Restricciones

Voy a agruparlas según tu numeración:

#### 4.0. Asignación inicial (semana 1)

- Separa motores propios (IDs 1…n_aviones) de los extras (IDs > n_aviones).
- Para cada motor propio `i` (i ≤ n_aviones):  
  - Se fuerza `a[i,i,1] == 1`: el motor i propio arranca en el avión i en t=1.  
  - Se fuerza `r[i,1] == 0` (no está en mantención al tiempo cero).  
  - Se fuerza `s[i,1] == 0` (no está en stock, porque ya está en vuelo).  
  - Para cualquier avión `p ≠ i`, `a[i,p,1] == 0`, para que no pueda “estar” simultáneamente en otro avión.  
- Para cada motor extra `i` (> n_aviones):  
  - `a[i,p,1] == 0` ∀ p: no está asignado aún, porque no compré ningún motor extra antes de semana 1.  
  - `r[i,1] == 0` y `s[i,1] == 0`: no está en mantención ni en stock.

**Objetivo de 4.0**: fijar el estado inicial del sistema (antes de semana 1, los motores propios ya están volando, y los extras no existen).

#### 4.1. “Estados exclusivos” de cada motor (propio vs. extra)

- Para cada motor `i` y cada semana `t`:  
  - Si `i` es motor extra:  
    ```
    sum_{p∈P_WB} a[i,p,t]  +  r[i,t]  +  s[i,t]
    =  sum_{τ=1..t} buy_extra[i,τ]
    ```
    *Interpretación*: Si no compré `i` antes de la semana `t`, el lado derecho es 0 y obliga a que `a+r+s = 0` (motor extra no “existe”). Una vez que `buy_extra[i,τ]=1` para alguna τ ≤ t, la suma de compras pasa a 1 y obliga a que `a+r+s = 1`, es decir, el motor extra esté en exactamente uno de esos estados (“asignado”, “en mantención” o “en stock”).  
  - Si `i` es motor propio:  
    ```
    sum_{p∈P_WB} a[i,p,t]  +  r[i,t]  +  s[i,t]  =  1
    ```
    Porque los motores propios siempre existen desde t=1, y cada semana están en un único estado.

#### 4.2. Cobertura de cada avión en cada semana

- Para cada avión `p` y semana `t`:  
  ```
  sum_{i∈I_WB} a[i,p,t]  +  ell[p,t]  =  1
  ```
  *Interpretación*: el avión `p` en la semana `t` o bien opera con algún motor `i` (∃ i tal que `a[i,p,t]=1`), o bien está rentando (`ell[p,t]=1`). No hay tercer estado; si no hay motor propio/extra disponible, `ell` debe valer 1 para “cubrirlo”.

#### 4.3. Duración del mantenimiento

- Para cada motor `i` y cada semana `t`:
  ```
  r[i,t]  =  sum_{tau = max(1, t-d+1) .. t} m[i, tau]
  ```
  *Interpretación*: `m[i,τ]=1` significa “inició mantención en la semana τ”. Si un motor inició en τ, estará en mantención durante d semanas consecutivas (τ, τ+1, …, τ+d-1). Esta restricción fuerza que `r[i,t]` sea exactamente 1 para cada t dentro de ese rango, porque el sumatorio de `m[i,τ]` se mantiene igual a 1 mientras τ ≤ t ≤ τ+d-1. Cuando pasa t = τ+d, el sumatorio “desliza” y ya no cuenta la mantención previa, entonces `r[i,t]` vuelve a 0.

#### 4.4. Acumulación de ciclos con reset en mantención

- Para cada motor `i`:
  - Semana 1:  
    ```
    y[i,1] = y0[i] + sum_{p∈P_WB} c[p] * a[i,p,1]
    ```
    Cálculo inicial: ciclos previos (y0) + ciclos que gana en la semana 1 según con qué avión esté asignado.  
  - Para t = 2…última:  
    - Defino `expr = sum_{p} c[p] * a[i,p,t]` (ciclos ganados esta semana t).  
    - Si t-d ≥ 1, hay posibilidad de que hace d semanas haya iniciado mantención. Entonces:
      ```
      y[i,t] = (1 - m[i,t-d]) * (y[i,t-1] + expr)  +  m[i,t-d] * (expr)
      ```
      - Si `m[i,t-d] = 0` entonces no inició mantención d semanas atrás, y la ecuación queda `y[i,t] = y[i,t-1] + expr`.  
      - Si `m[i,t-d] = 1` (inició mantención en t-d), entonces ahora en t se “resetean” los ciclos previos y `y[i,t] = expr`.  
    - Si t-d < 1 (aún no ha existido ninguna mantención que termine a esa altura), simplemente:
      ```
      y[i,t] = y[i,t-1] + expr
      ```

#### 4.5. Límite estricto de ciclos tras mantención

- Para cada motor `i` y semana `t`:  
  ```
  y[i,t] ≤ C[i]  +  M * r[i,t]
  ```
  Aquí `M` es un número muy grande (por ejemplo, el máximo de todos los umbrales) que permite que durante la semana que está en mantención (`r[i,t]=1`) el límite se relaje:  
  - Si `r[i,t]=0` → obliga `y[i,t] ≤ C[i]`.  
  - Si `r[i,t]=1` → obliga `y[i,t] ≤ C[i] + M` (prácticamente no hay restricción, porque M es grande).  

  Esto garantiza que el motor no sobrepase su umbral **en semanas en las que no está en mantención**.

#### 4.6. Capacidad de inicios de mantención

- Para cada semana `t`:  
  ```
  sum_{i∈I_WB} m[i,t] ≤ M_max
  ```
  Es decir, en cada semana a lo más `M_max` motores pueden comenzar mantención.

#### 4.7. Flujo de inventario de repuestos (stock)

- Semana 1:
  ```
  S[1] = S0  +  sum_{i∈I_extra} buy_extra[i,1]
  ```
  Arrancamos con stock inicial `S0` (que suele ser 0) y sumamos los motores extras que compramos en la semana 1.  
- Para t = 2…última:
  ```
  S[t] = S[t-1]
        + sum_{i∈I_extra} buy_extra[i,t]    (nuevas compras esta semana)
        + sum_{i∈I_WB where t-d>0} m[i,t-d]  (motores que terminan mantención esta semana, pues iniciaron en t-d)
  ```
  De este modo, cada vez que algún motor sale de mantención, vuelve al stock y se suma uno.

#### 4.8. Continuidad de asignación

- Para cada motor `i`, avión `p` y t = 2…última:
  ```
  a[i,p,t] ≥ a[i,p,t-1] – m[i,t]
  ```
  Esto implica:
  - Si `a[i,p,t-1] = 1` (i estaba en p en la semana anterior) y `m[i,t] = 0` (no entró en mantención en t), entonces `a[i,p,t] ≥ 1`, forzando `a[i,p,t] = 1`: el motor sigue en el mismo avión.  
  - Si `m[i,t] = 1` (entra a mantención en t), entonces `a[i,p,t] ≥ a[i,p,t-1] - 1`. Si antes estaba con ese avión, ahora ya no está; la desigualdad queda `a[i,p,t] ≥ 0`, lo cual no fuerza asignación.  

  **Objetivo**: no permitir movimientos “libres” de motor arbitrariamente, salvo si entró en mantención.

#### 4.9. Solo stock si compré (motores extra)

- Para cada motor extra `i` y semana `t`:  
  ```
  s[i,t] ≤ sum_{τ=1..t} buy_extra[i,τ]
  ```
  Si no he comprado `i` antes de la semana `t`, el sumatorio es 0 y obliga a `s[i,t] = 0`. Solo después de alguna compra previa `buy_extra[i,τ]` puedo tener `s[i,t] = 1`.

#### 4.10. Solo asignar motor extra si ya está comprado

- Para `i ∈ I_extra, p ∈ P_WB, t ∈ T`:
  ```
  a[i,p,t] ≤ sum_{τ=1..t} buy_extra[i,τ]
  ```
  Análogo a 4.9: si no he comprado el motor yet, no puede asignarse a ningún avión.

#### 4.11. Si compro motor extra, se usa en la misma semana

- Para `i ∈ I_extra, t ∈ T`:
  ```
  sum_{p∈P_WB} a[i,p,t]  ≥  buy_extra[i,t]
  ```
  Esto obliga a que si `buy_extra[i,t] = 1`, entonces el motor extra debe inmediatamente asignarse a algún avión `p` en esa misma semana (∃ p con `a[i,p,t]=1`). Si no, la desigualdad no se cumple.

#### 4.12. Cada motor extra solo se compra una vez

- Para cada extra `i`:
  ```
  sum_{t ∈ T} buy_extra[i,t]  ≤  1
  ```
  Así no permitimos comprar el mismo motor en dos semanas diferentes.

#### 4.13. Restricciones de “semanas impares” (heurística)

Este bloque básicamente recrea el código que
…

---

*Continúa la explicación con el detalle de cada restricción y la función objetivo.*
