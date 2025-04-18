import streamlit as st
import pandas as pd
import re
from io import BytesIO

# ——————————————————————————————————————————————
# Funciones de limpieza
# ——————————————————————————————————————————————

def clean_code(x):
    """
    Normaliza un código SKU de cualquier formato:
    1) Si viene como float “12345.0” lo convierte a “12345”
    2) Elimina todo carácter no numérico (guiones, espacios, puntos, etc.)
    """
    s = str(x).strip()
    try:
        f = float(s)
        if f.is_integer():
            s = str(int(f))
        else:
            s = str(f)
    except:
        pass
    # Solo dígitos
    return re.sub(r'\D', '', s)

def to_float_series(ser):
    """
    Convierte una serie a float:
    - Reemplaza comas por puntos
    - Coerce errores a NaN
    """
    return pd.to_numeric(
        ser.astype(str).str.replace(",", ".", regex=False),
        errors="coerce"
    )

# ——————————————————————————————————————————————
st.title("Actualización de Costos")
st.markdown("""
Sube el **EXCEL DESCARGADO DE RELBASE** y los listados de precios.
Cada empresa puede tener:
- Hoja distinta  
- Fila de encabezado distinta  
- Columnas de código y precio distintas  
- Descuento propio  

La aplicación limpiará automáticamente códigos y precios para que coincidan.
""")

# 1. Carga del Excel maestro
master_file = st.file_uploader("1. Sube aqui el **EXCEL DE RELBASE** (productos de bodega)", type=["xlsx"])
if not master_file:
    st.stop()

df_master = pd.read_excel(master_file)
df_master.columns = df_master.columns.astype(str)
df_master["CODIGO_CLEAN"] = (
    df_master["CODIGO SKU"]
      .astype(str)
      .str.split("/", n=1).str[0]
      .map(clean_code)
)

# 2. Carga de múltiples listados de precios
price_files = st.file_uploader(
    "2. Sube los listados de precios. Puedes subir **más de un excel a la vez**",
    type=["xlsx"],
    accept_multiple_files=True
)
if not price_files:
    st.stop()

mappings   = []  # Cada mapping: código -> precio efectivo
stats_list = []  # Stats de cada empresa

# 3. Configuración por empresa
for idx, price_file in enumerate(price_files):
    with st.expander(f"Empresa #{idx+1}: {price_file.name}", expanded=True):
        # Selección de hoja
        xls = pd.ExcelFile(price_file)
        sheet = st.selectbox("Indica en que hoja se encuentra el listado de precios:", xls.sheet_names, key=f"sheet_{idx}")
        
        # Vista previa sin encabezado: índice ajustado para usuario
        df_prev = pd.read_excel(price_file, sheet_name=sheet, header=None)
        df_prev.columns = df_prev.columns.map(str)
        df_prev.index = df_prev.index + 1  # shift index so it shows 1,2,3...
        st.write("Vista previa (primeras 20 filas):")
        sub = df_prev.head(20)
        # reconstrúyelo para mantener ese índice visual
        clean_prev = pd.DataFrame(sub.values, columns=sub.columns, index=sub.index)
        st.dataframe(clean_prev)
        
        # Fila de encabezado
        header_row = st.number_input(
            "Indica en que fila esta el **ENCABEZADO** del listado:",
            min_value=1, value=1, step=1, key=f"hdr_{idx}"
        )
        
        # Leer datos con encabezado, y mostrar sin índice
        df_prices = pd.read_excel(
            price_file, sheet_name=sheet, header=header_row-1
        )
        df_prices.columns = df_prices.columns.astype(str)
        st.write("Listado de precios:")
        sub2 = df_prices.head(20)
        clean2 = pd.DataFrame(sub2.values, columns=sub2.columns)
        st.dataframe(clean2)
        
        # Selección de columnas y descuento
        cols      = df_prices.columns.tolist()
        code_col  = st.selectbox("Indique columna del código de los productos **(ISBN)**:", cols, key=f"code_{idx}")
        price_col = st.selectbox("Indique columna del nuevo precio de los productos:", cols, key=f"price_{idx}")
        discount  = st.number_input(
            "Descuento (%) para esta empresa",
            min_value=0.0, value=0.0, step=0.1, key=f"disc_{idx}"
        )
        
        # Limpieza de códigos
        df_prices[code_col] = df_prices[code_col].map(clean_code)
        
        # Conversión de precios a float
        df_prices[price_col] = to_float_series(df_prices[price_col])
        
        # Validar que haya precios
        if df_prices[price_col].notna().sum() == 0:
            st.warning("⚠️ La columna de nuevo costo no tiene valores numéricos válidos. Selecciona otra.")
            continue
        
        # Construir mapping
        mapping = {}
        for _, row in df_prices.iterrows():
            code  = row[code_col]
            price = row[price_col]
            if pd.isna(price) or code == "":
                continue
            mapping[code] = price * (1 - discount/100)
        
        # Estadísticas por empresa
        codes_set = set(mapping.keys())
        coinc = df_master["CODIGO_CLEAN"].isin(codes_set).sum()
        mods  = sum(
            1 for _, r in df_master.iterrows()
            if r["CODIGO_CLEAN"] in mapping
               and mapping[r["CODIGO_CLEAN"]] != r["COSTO PROMEDIO ACTUAL"]
        )
        st.success(f"✔️ {price_file.name}: {coinc} coincidencias, {mods} modificados.")
        
        mappings.append(mapping)
        stats_list.append({"name": price_file.name, "coinc": coinc, "mods": mods})

# 4. Botón de procesamiento y descarga
if st.button("Actualizar Excel maestro"):
    # Combina todos los mappings
    global_map = {}
    for m in mappings:
        global_map.update(m)
    
    # Función que fija el nuevo costo o deja 0
    def update_cost(row):
        code = row["CODIGO_CLEAN"]
        curr = row["COSTO PROMEDIO ACTUAL"]
        if code in global_map:
            newp = global_map[code]
            return 0 if newp == curr else newp
        return 0
    
    df_master["NUEVO COSTO PROMEDIO"] = df_master.apply(update_cost, axis=1)
    
    # Estadísticas finales
    total_coinc = sum(s["coinc"] for s in stats_list)
    total_mods  = sum(s["mods"]  for s in stats_list)
    
    st.success("✅ Procesamiento completo.")
    st.markdown("**Por empresa:**")
    for s in stats_list:
        st.info(f"- {s['name']}: {s['coinc']} coincidencias, {s['mods']} modificados")
    st.markdown(f"**Totales:** {total_coinc} coincidencias, {total_mods} modificaciones.")
    
    # Preparar y descargar
    df_export = df_master.drop(columns=["CODIGO_CLEAN"])
    buf = BytesIO()
    df_export.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    st.download_button(
        "Descargar Excel maestro actualizado",
        data=buf,
        file_name="Excel_maestro_actualizado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )