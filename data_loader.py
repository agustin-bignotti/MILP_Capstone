# data_loader.py
import pandas as pd
import os
import sys

def load_data(data_path='Datos/'):

    # Normaliza data_path para que no acabe (o empiece) con slash redundante:
    data_path = data_path.rstrip('/')

    required_files = [
        'Fleet_status_WB.csv',
        'Operations_cycles_WB.csv',
        'Max_cycles_WB.csv',
        'Motor_info.csv'
    ]
    for fn in required_files:
        full = os.path.join(data_path, fn)
        if not os.path.isfile(full):
            print(f"ERROR: No encontré {full}", file=sys.stderr)
            sys.exit(1)

    # 1. Cargar CSV de flota wide‐body
    df_status_wb = pd.read_csv(f'{data_path}/Fleet_status_WB.csv')
    # Asignar IDs secuenciales según línea de archivo (1…n)
    df_status_wb.insert(0, 'id', range(1, len(df_status_wb) + 1))

    # Motores para Comprar
    n_extra = 3
    n_aviones = len(df_status_wb)
    P_WB = list(range(1, n_aviones + 1))

    # Conjuntos de IDs
    I_extra = list(range(n_aviones + 1, n_aviones + n_extra + 1))
    I_WB = list(range(1, n_aviones + 1)) + I_extra
    T = list(range(1, 55))  # 54 semanas

    # Mapeos matricula ↔ id
    mat2id = dict(zip(df_status_wb['matricula'], df_status_wb['id']))
    id2mat = {i: m for m, i in mat2id.items()}
    for i in I_extra:
        id2mat[i] = f"EXTRA_{i}"  

    # Leer ciclos diarios y convertir a semanales
    df_cycles_wb = pd.read_csv(f'{data_path}/Operations_cycles_WB.csv')
    df_cycles_wb['ac_norm'] = (
        df_cycles_wb['Aircraft']
        .str.replace(r'[-\s]', '', regex=True)
        .str.upper()
    )
    df_cycles_wb['cycles_per_week'] = df_cycles_wb['Value'] * 7
    rate_map = dict(zip(df_cycles_wb['ac_norm'], df_cycles_wb['cycles_per_week']))

    # Normalizar operación en df_status
    df_status_wb['op_norm'] = (
        df_status_wb['Operation']
        .str.replace(r'[-\s]', '', regex=True)
        .str.upper()
    )

    # Construir c[id] = ciclos/semana para cada avión ID
    c = {}
    for _, row in df_status_wb.iterrows():
        op = row['op_norm']
        match = next((code for code in rate_map if op.startswith(code)), None)
        if match is None:
            raise KeyError(f"No encontré tasa para operación '{row['Operation']}'")
        c[row['id']] = rate_map[match]

    # Ciclos iniciales y umbrales
    y0 = dict(zip(df_status_wb['id'], df_status_wb['cycles']))

    df_max_wb = pd.read_csv(f'{data_path}/Max_cycles_WB.csv')
    df_max_wb['code_norm'] = (
        df_max_wb['Aircraft_family']
        .str.replace(r'[-\s]', '', regex=True)
        .str.upper()
    )
    C_f = dict(zip(df_max_wb['code_norm'], df_max_wb['Max cycles']))

    C = {}
    for _, row in df_status_wb.iterrows():
        op = row['op_norm']
        fam = next((code for code in C_f if op.startswith(code)), None)
        if fam is None:
            raise KeyError(f"No umbral para operación '{row['Operation']}'")
        C[row['id']] = C_f[fam]

    # Parámetros económicos y constantes
    df_motor_info = pd.read_csv(f'{data_path}/Motor_info.csv')
    LeaseCost = int(df_motor_info.loc[df_motor_info['Action']=='Lease for week','Price'].iloc[0])
    BuyCost   = int(df_motor_info.loc[df_motor_info['Action']=='Buy','Price'].iloc[0])
    d         = 18
    S0        = 0
    M_max     = 5
    M         = max(C.values())

    # Extender parametros para los motores extras
    for i in I_extra:
        y0[i] = 0
        C[i] = M

    print("✅ Datos cargados.")

    params = {
        # DataFrames (si más adelante los necesitas para debug o para reportes extra)
        "df_status_wb": df_status_wb,
        "df_cycles_wb": df_cycles_wb,
        "df_max_wb": df_max_wb,
        "df_motor_info": df_motor_info,

        # Conjuntos y listas
        "P_WB": P_WB,
        "I_WB": I_WB,
        "I_extra": I_extra,
        "T": T,

        # Mapeos y diccionarios
        "mat2id": mat2id,
        "id2mat": id2mat,
        "c": c,
        "C": C,
        "y0": y0,

        # Parámetros económicos
        "LeaseCost": LeaseCost,
        "BuyCost": BuyCost,
        "d": d,
        "S0": S0,
        "M_max": M_max,
        "M": M,
    }

    return params
