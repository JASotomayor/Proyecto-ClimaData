# ClimaData Rural Point Analyzer

Aplicacion web en Streamlit para analizar un punto geografico rural a partir de
un enlace de Google Maps, coordenadas manuales o seleccion en mapa. La primera
version prioriza robustez, utilidad practica y lectura agronomica prudente con
fuentes abiertas y gratuitas.

## Que hace esta version

- Extrae coordenadas desde enlaces largos de Google Maps o desde texto `lat,lon`.
- Permite cargar coordenadas manuales.
- Permite mover el punto desde un mapa interactivo.
- Consulta clima historico diario con NASA POWER.
- Resume lluvia, temperatura, variabilidad, heladas y ranking de anos.
- Consulta suelos estimados con SoilGrids como fuente principal actual.
- Evalua relieve local y un indicador indirecto de drenaje con una API abierta de elevacion.
- Genera enlaces directos a Google Maps satelite y EO Browser.
- Produce un resumen ejecutivo simple para compartir.
- Incluye una pestana de aptitud agroclimatica para escenarios extensivos.
- Incluye una primera capa ML complementaria para maiz temprano cuando existe un modelo entrenado.
- Ya incorpora escenarios activos para:
  - maiz temprano
  - maiz tardio
  - trigo
  - soja de primera
  - soja de segunda
- Compara escenarios de una misma especie bajo el mismo punto y rango historico.

## Estructura del proyecto

```text
project/
  app.py
  src/
    __init__.py
    agro_scores.py
    climate.py
    climate_compare.py
    climate_models.py
    climate_processing.py
    config.py
    crops.py
    eto.py
    fao.py
    ml_dataset.py
    ml_features.py
    ml_predict.py
    ml_train.py
    parsers.py
    reporting.py
    satellite.py
    soil.py
    terrain.py
    ui.py
    utils.py
  data/
    example_points.csv
  assets/
    custom.css
  tests/
    test_parsers.py
  requirements.txt
  README.md
```

## Requisitos

- Python 3.11 o superior recomendado
- Acceso a internet para consultar NASA POWER, SoilGrids y elevacion

## Instalacion local

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Ejecucion

```bash
streamlit run app.py
```

La app arranca con el punto de ejemplo:

```text
-35.557091, -63.599219
```

## Como usarla

1. En la sidebar pega un enlace de Google Maps o unas coordenadas.
2. O bien ajusta latitud y longitud manualmente.
3. O bien haz clic sobre el mapa para reemplazar el punto.
4. Elige el rango temporal climatico.
5. Revisa el resumen, clima, suelos, relieve y enlaces satelitales.
6. En la pestana `Aptitud agroclimatica`, elige el sistema de cultivo y revisa:
   - score medio
   - balance del ciclo
   - balance de etapas criticas
   - comparacion historica entre escenarios de la misma especie

## Notas metodologicas

- El riesgo de helada se estima con una logica simple basada en Tmin media mensual.
- El riesgo de anegamiento es solo una inferencia indirecta usando relieve local.
- La napa freatica no puede confirmarse con precision solo con fuentes online.
- La integracion con servicios de INTA no se fuerza en esta version para no volver la app fragil.
- La aptitud agroclimatica es una lectura climatico-hidrica relativa y no una prediccion de rendimiento.
- La ETc se calcula con un enfoque FAO simplificado y el metodo ETo usado queda explicitado en la UI.
- Los escenarios productivos deben leerse junto con fecha real de siembra, suelo util, napa, manejo y objetivo agronomico.
- La capa ML actual aprende sobre etiquetas del baseline agronomico; complementa la lectura, no reemplaza la trazabilidad FAO.

## Flujo ML offline

La primera version ML queda desacoplada de la app y orientada a `maize_early`,
`maize_late`, `soy_first`, `soy_second` y `wheat`.

1. Generar dataset de features por campana desde puntos reales:

```bash
python -m src.ml_dataset --points data/ml_points_extensivos_argentina.csv --scenario maize_early --start-year 2005 --end-year 2024
```

2. Entrenar y persistir el clasificador:

```bash
python -m src.ml_train --features data/ml/maize_early_2005_2024_campaign_features.csv --scenario maize_early --model-type gradient_boosting
```

3. Evaluar el modelo con validacion cruzada, holdout temporal y holdout por punto:

```bash
python -m src.ml_evaluate --features data/ml/maize_early_2005_2024_campaign_features.csv --scenario maize_early --model-type gradient_boosting
```

4. Repetir el mismo flujo para `maize_late`, `soy_first`, `soy_second` o `wheat`
   cuando se quiera entrenar las siguientes capas ML:

```bash
python -m src.ml_dataset --points data/ml_points_extensivos_argentina.csv --scenario maize_late --start-year 2005 --end-year 2024
python -m src.ml_train --features data/ml/maize_late_2005_2024_campaign_features.csv --scenario maize_late --model-type gradient_boosting
python -m src.ml_evaluate --features data/ml/maize_late_2005_2024_campaign_features.csv --scenario maize_late --model-type gradient_boosting

python -m src.ml_dataset --points data/ml_points_extensivos_argentina.csv --scenario soy_first --start-year 2005 --end-year 2024
python -m src.ml_train --features data/ml/soy_first_2005_2024_campaign_features.csv --scenario soy_first --model-type gradient_boosting
python -m src.ml_evaluate --features data/ml/soy_first_2005_2024_campaign_features.csv --scenario soy_first --model-type gradient_boosting

python -m src.ml_dataset --points data/ml_points_extensivos_argentina.csv --scenario soy_second --start-year 2005 --end-year 2024
python -m src.ml_train --features data/ml/soy_second_2005_2024_campaign_features.csv --scenario soy_second --model-type gradient_boosting
python -m src.ml_evaluate --features data/ml/soy_second_2005_2024_campaign_features.csv --scenario soy_second --model-type gradient_boosting

python -m src.ml_dataset --points data/ml_points_extensivos_argentina.csv --scenario wheat --start-year 2005 --end-year 2024
python -m src.ml_train --features data/ml/wheat_2005_2024_campaign_features.csv --scenario wheat --model-type gradient_boosting
python -m src.ml_evaluate --features data/ml/wheat_2005_2024_campaign_features.csv --scenario wheat --model-type gradient_boosting
```

5. Si el modelo existe en `data/models/maize_early/`, `data/models/maize_late/`
   `data/models/soy_first/`, `data/models/soy_second/` o `data/models/wheat/`,
   la pestana `Aptitud agroclimatica` muestra una lectura ML complementaria para esos escenarios.

## Despliegue en Streamlit Community Cloud

1. Sube este proyecto a un repositorio Git.
2. Verifica que `app.py`, `requirements.txt` y `.streamlit/config.toml` esten versionados.
3. Crea una app en Streamlit Community Cloud apuntando a `app.py`.
4. En el panel de Streamlit selecciona una version moderna de Python compatible con `pandas>=2.2`.
5. Despliega y revisa que la app pueda acceder a NASA POWER, SoilGrids y OpenTopoData.

## Checklist de despliegue

- `requirements.txt` en la raiz del repo.
- `.streamlit/config.toml` presente para configuracion consistente.
- No se requieren secretos ni APIs de pago en esta v1.
- Si una fuente externa falla, la app sigue operativa con mensajes claros y fallbacks.

## Recomendaciones operativas para Streamlit Cloud

- Mantener el rango temporal por defecto en 10 anos para reducir tiempos de consulta.
- Si una fuente externa se vuelve inestable, reintentar la carga antes de asumir un error permanente.
- Para una demo publica, conviene fijar un punto de ejemplo conocido y explicar que napa y suelo son estimaciones indirectas.

## Siguientes evoluciones sugeridas

- Calibracion del score agroclimatico con mas casos reales por escenario.
- Comparacion metodologica entre fuentes climaticas.
- Comparacion entre escenarios productivos dentro de un mismo punto con mayor robustez narrativa.
- Poligonos de lote en lugar de solo punto.
- Series NDVI y analisis multitemporal.
- Comparacion entre puntos.
- Exportacion PDF o informe imprimible.
