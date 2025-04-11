import streamlit as st
import pandas as pd
from io import BytesIO

st.title("Actualización de Costos en Inventario")
st.markdown("""
Esta aplicación te permite actualizar el costo de los productos en el Excel maestro utilizando 
un listado de nuevos precios.

**Notas importantes:**
- En el Excel maestro, el **CODIGO SKU** puede incluir texto adicional tras la barra "/".  
  Para la comparación interna, solo se usará la parte anterior a la barra.
- Solo se actualizará la columna **NUEVO COSTO PROMEDIO**.
- Si el nuevo precio, tras aplicar un descuento, coincide con el **COSTO PROMEDIO ACTUAL**, se dejará un 0 
  en **NUEVO COSTO PROMEDIO** (indicando que no se modificó).
""")

# 1. Subida del Excel maestro
master_file = st.file_uploader("1. Sube el Excel maestro (productos de bodega)", type=["xlsx", "xls"])

# 2. Subida del Excel de nuevos precios
new_prices_file = st.file_uploader("2. Sube el Excel con el listado de nuevos precios", type=["xlsx", "xls"])

if master_file and new_prices_file:
    # --- Procesar el Excel maestro (no se muestra la vista previa) ---
    df_master = pd.read_excel(master_file)
    # Forzar que los nombres de columnas en el excel maestro sean strings (por si acaso)
    df_master.columns = df_master.columns.astype(str)
    
    # Crear la columna auxiliar "CODIGO_CLEAN" extrayendo la parte anterior a la barra "/"
    df_master["CODIGO_CLEAN"] = (
        df_master["CODIGO SKU"]
        .astype(str)
        .str.split("/")
        .str[0]
        .str.strip()
    )

    st.subheader("Indica en que fila comienza el listado de precios")
    st.write("Se muestran las primeras 20 filas, si la lista comienza más abajo, ingrese el número de fila donde inicia.")
    
    # --- Lectura preliminar sin encabezado para mostrar vista previa con índice ajustado ---
    df_preview = pd.read_excel(new_prices_file, header=None)
    # Convertir los nombres de columnas a string para evitar errores en la conversión
    df_preview.columns = df_preview.columns.map(str)
    df_preview.index += 1  # Ajuste para que el índice empiece en 1
    st.dataframe(df_preview.head(20))
    
    # --- Solicitar al usuario la fila en la que se encuentra el título de la tabla ---
    header_row = st.number_input(
        "¿En qué fila se encuentra el título de la tabla?",
        min_value=1,
        value=1,
        step=1
    )
    
    # --- Lectura del Excel de nuevos precios usando la fila indicada como encabezado ---
    df_new_prices = pd.read_excel(new_prices_file, header=header_row - 1)
    # Convertir los nombres de columnas a string para evitar errores posteriores
    df_new_prices.columns = df_new_prices.columns.astype(str)
    
    st.subheader("Tabla de listado de precios")
    st.dataframe(df_new_prices.head(20))
    
    # Solicitar el porcentaje de descuento (por defecto 0%)
    discount = st.number_input("Ingresa el porcentaje de descuento (%)", min_value=0.0, value=0.0, step=0.1)
    
    # Selección de columnas del listado
    new_prices_cols = df_new_prices.columns.tolist()
    code_column = st.selectbox(
        "Selecciona la columna que contiene el **Código del Producto**",
        new_prices_cols
    )
    price_column = st.selectbox(
        "Selecciona la columna que contiene el **Nuevo Costo**",
        new_prices_cols
    )
    
    if st.button("Actualizar Excel maestro"):
        # Normalizar los códigos en el listado de nuevos precios
        df_new_prices[code_column] = df_new_prices[code_column].astype(str).str.strip()
        
        # Crear diccionario de mapeo: código (tal como aparece en el listado) -> nuevo costo
        new_cost_mapping = df_new_prices.set_index(code_column)[price_column].to_dict()
        
        # Calcular la cantidad de coincidencias (usando la columna "CODIGO_CLEAN")
        coincidence_count = df_master["CODIGO_CLEAN"].isin(new_cost_mapping.keys()).sum()
        
        # Función para actualizar el costo:
        # Se obtiene el nuevo precio del listado, se le aplica el descuento
        # y se compara con el "COSTO PROMEDIO ACTUAL". Si son iguales, se deja 0.
        def update_cost(row):
            code_clean = row["CODIGO_CLEAN"]
            current_cost = row["COSTO PROMEDIO ACTUAL"]
            if code_clean in new_cost_mapping:
                new_price = new_cost_mapping[code_clean]
                # Calcular el precio efectivo tras aplicar el descuento
                effective_price = new_price * (1 - discount / 100)
                if effective_price == current_cost:
                    return 0
                else:
                    return effective_price
            else:
                return 0
        
        df_master["NUEVO COSTO PROMEDIO"] = df_master.apply(update_cost, axis=1)
        
        # Contar cuántos productos se modificaron (valor distinto de 0 en "NUEVO COSTO PROMEDIO")
        modified_count = (df_master["NUEVO COSTO PROMEDIO"] != 0).sum()
        
        st.success("Excel maestro actualizado con los nuevos costos.")
        st.info(f"{coincidence_count} libros hay en coincidencia. {modified_count} libros fueron modificados ya que los demás mantuvieron el precio de lista.")
        
        # Eliminar la columna auxiliar antes de exportar
        df_export = df_master.drop(columns=["CODIGO_CLEAN"])
        
        # Preparar el archivo Excel para descarga
        towrite = BytesIO()
        df_export.to_excel(towrite, index=False, engine="openpyxl")
        towrite.seek(0)
        
        st.download_button(
            label="Descargar Excel maestro actualizado",
            data=towrite,
            file_name="Excel_maestro_actualizado.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
