import streamlit as st
import pandas as pd
import re
from io import BytesIO

# ——————————————————————————————————————————————
# Página en modo ancho
# ——————————————————————————————————————————————
st.set_page_config(layout="wide")

# ——————————————————————————————————————————————
# Inyección de CSS para estilos con bordes de menor contraste
# ——————————————————————————————————————————————
st.markdown("""
<style>
/* Botones con color y bordes suavizados */
.stButton>button {
  background-color: #1976d2;
  color: white;
  border-radius: 5px;
}

/* Zonas de carga de archivos con padding extra y borde más suave */
input[type="file"] {
  background-color: #e3f2fd !important;
  border: 2px dashed #7fa8cc !important;   /* celeste más suave */
  border-radius: 5px !important;
  padding: 20px !important;
}

/* Selectboxes con borde más suave */
div[data-baseweb="select"] > div > div {
  border: 2px solid #7fa8cc !important;     /* celeste más suave */
  border-radius: 5px !important;
}

/* Number inputs con borde más suave */
input[type="number"] {
  border: 2px solid #7fa8cc !important;     /* celeste más suave */
  border-radius: 5px !important;
  padding: 6px !important;
}

/* Encabezados de expander más grandes y con padding */
.stExpanderHeader {
  background-color: #e1f5fe !important;
  border-radius: 4px;
  font-size: 1.1rem !important;
  padding: 0.75rem !important;
}

/* Contenido de expander con más padding */
.stExpanderContent {
  padding: 1rem !important;
}

/* Subheaders más grandes */
h2 {
  font-size: 1.3rem !important;
}

/* Padding adicional en sidebar */
[data-testid="stSidebar"] > div:first-child {
  padding: 1rem !important;
}
</style>
""", unsafe_allow_html=True)

# ——————————————————————————————————————————————
# Funciones de limpieza
# ——————————————————————————————————————————————
def clean_code(x):
    s = str(x).strip()
    try:
        f = float(s)
        s = str(int(f)) if f.is_integer() else str(f)
    except:
        pass
    return re.sub(r'\D', '', s)

def to_float_series(ser):
    return pd.to_numeric(
        ser.astype(str).str.replace(",", ".", regex=False),
        errors="coerce"
    )

# ——————————————————————————————————————————————
# Caching para lecturas
# ——————————————————————————————————————————————
@st.cache_data
def load_master(file):
    df = pd.read_excel(file)
    df.columns = df.columns.astype(str)
    df["CODIGO_CLEAN"] = (
        df["CODIGO SKU"].astype(str)
          .str.split("/", n=1).str[0]
          .map(clean_code)
    )
    return df

@st.cache_data
def load_preview(file, sheet):
    df = pd.read_excel(file, sheet_name=sheet, header=None)
    df.columns = df.columns.map(str)
    df.index = df.index + 1
    return df

@st.cache_data
def load_prices(file, sheet, header_row):
    df = pd.read_excel(file, sheet_name=sheet, header=header_row - 1)
    df.columns = df.columns.astype(str)
    return df

# ——————————————————————————————————————————————
# Sidebar: carga de archivos
# ——————————————————————————————————————————————
st.sidebar.title("_Actualización de costos_")
st.sidebar.markdown(
    "1️⃣ Sube aqui el **EXCEL DE RELBASE** (productos de bodega)"
)
master_file = st.sidebar.file_uploader("Excel descargado de RelBase:", type=["xlsx"])
st.sidebar.markdown(
    "2️⃣ Sube uno o más listados de precios (.xlsx)"
)
price_files = st.sidebar.file_uploader(
    "Listados de precios:", type=["xlsx"], accept_multiple_files=True
)
if not master_file or not price_files:
    st.sidebar.warning("Sube el excel de RelBase y al menos un listado de precios.")
    st.stop()

# ——————————————————————————————————————————————
# Cargar datos maestros
# ——————————————————————————————————————————————
df_master = load_master(master_file)

# ——————————————————————————————————————————————
# Proceso por empresa
# ——————————————————————————————————————————————
mappings   = []
stats_list = []

st.header("Configuración por Empresa")
for idx, pf in enumerate(price_files):
    with st.expander(f"Empresa #{idx+1}: {pf.name}", expanded=True):
        xls = pd.ExcelFile(pf)
        sheet = st.selectbox("Indica en que hoja se encuentra el listado de precios:", xls.sheet_names, key=f"sheet_{idx}")

        df_prev = load_preview(pf, sheet)
        st.write("Vista previa (primeras 20 filas):")
        st.dataframe(df_prev.head(20))

        header_row = st.number_input(
            "Indica en que fila esta el **ENCABEZADO** del listado:", min_value=1, value=1, step=1, key=f"hdr_{idx}"
        )

        df_prices = load_prices(pf, sheet, header_row)
        st.write("Listado de precios:")
        clean2 = pd.DataFrame(df_prices.head(20).values, columns=df_prices.columns)
        st.dataframe(clean2)

        cols      = df_prices.columns.tolist()
        code_col  = st.selectbox("Indique columna del código de los productos **(ISBN)**:",  cols, key=f"code_{idx}")
        price_col = st.selectbox("Indique columna del nuevo precio de los productos:",   cols, key=f"price_{idx}")
        discount  = st.number_input(
            "Descuento (%) para esta empresa:", min_value=0.0, value=0.0, step=0.1, key=f"disc_{idx}"
        )

        df_prices[code_col]  = df_prices[code_col].map(clean_code)
        df_prices[price_col] = to_float_series(df_prices[price_col])

        if df_prices[price_col].notna().sum() == 0:
            st.warning("⚠️ Columna de precio no son valores numéricos. Elige otra.")
            continue

        mapping = {}
        for _, row in df_prices.iterrows():
            c = row[code_col]
            p = row[price_col]
            if pd.isna(p) or c == "":
                continue
            mapping[c] = p * (1 - discount/100)

        codes_set = set(mapping.keys())
        coinc = df_master["CODIGO_CLEAN"].isin(codes_set).sum()
        mods  = sum(
            1 for _, r in df_master.iterrows()
            if r["CODIGO_CLEAN"] in mapping
               and mapping[r["CODIGO_CLEAN"]] != r["COSTO PROMEDIO ACTUAL"]
        )
        st.success(f"✔️ {pf.name}: **{coinc}** coincidencias, **{mods}** modificados.")

        mappings.append(mapping)
        stats_list.append({"name": pf.name, "coinc": coinc, "mods": mods})

# ——————————————————————————————————————————————
# Actualizar y descargar
# ——————————————————————————————————————————————
if st.button("Actualizar Excel maestro"):
    global_map = {}
    for m in mappings:
        global_map.update(m)

    def update_cost(row):
        code = row["CODIGO_CLEAN"]
        curr = row["COSTO PROMEDIO ACTUAL"]
        if code not in global_map:
            return 0
        return 0 if global_map[code] == curr else global_map[code]

    df_master["NUEVO COSTO PROMEDIO"] = df_master.apply(update_cost, axis=1)

    total_coinc = sum(s["coinc"] for s in stats_list)
    total_mods  = sum(s["mods"]  for s in stats_list)

    st.success("✅ Procesamiento completo.")
    st.markdown("**Estadísticas por empresa:**")
    for s in stats_list:
        st.info(f"- {s['name']}: {s['coinc']} coincidencias, {s['mods']} modificados")
    st.markdown(f"**Totales:** {total_coinc} coincidencias, {total_mods} modificaciones.")

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
