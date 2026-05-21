# SIAPV-API

API del Sistema Integrado de Adquisición, Procesamiento, Validación y Visualización de Datos Geomagnéticos —SIAPV—, desarrollada para el manejo de información geomagnética del Observatorio Geomagnético de Fúquene (FUQ), Colombia.

El sistema permite integrar procesos de consulta, procesamiento y visualización de datos geomagnéticos en tiempo casi real, incluyendo el manejo de archivos de línea base, selección de días quietos, construcción de curvas de variación solar regular y generación de productos asociados al monitoreo geomagnético.

## Descripción general

SIAPV-API está construida en Python y utiliza FastAPI para exponer servicios asociados al procesamiento de información geomagnética. El sistema se orienta principalmente al tratamiento de datos del Observatorio de Fúquene, integrando rutinas de adquisición, procesamiento, validación y visualización.

Entre sus funcionalidades principales se incluyen:

- Consulta y procesamiento de datos geomagnéticos.
- Lectura de archivos de línea base en formato BLV.
- Manejo de series temporales geomagnéticas.
- Selección de días quietos.
- Construcción de curvas de variación solar regular.
- Generación de productos gráficos para análisis.
- Integración con una interfaz web estática.
- Apoyo al cálculo y visualización de índices geomagnéticos en tiempo casi real.

## Estructura del repositorio

```text
SIAPV-API/
│
├── api.py
│
├── baseline/
│   ├── Leer_baseline.py
│   ├── __init__.py
│   └── data_blv/
│       └── FUQ2025.blv
│
├── sq/
│   ├── sq_io.py
│   ├── sq_model.py
│   ├── sq_quiet.py
│   └── sq_state.py
│
├── static/
│   ├── index.html
│   ├── SIAPV.png
│   ├── IGAC_LOGO.png
│   ├── UD.png
│   ├── GOSA.png
│   └── logo.png
│
├── graficar_k_rt.py
├── sr_curve_vs_k.py
├── test_sq_local.py
│
├── requirements.txt
├── .env.example
├── .gitignore
├── LICENSE
└── README.md

## Instalación rápida

Clonar el repositorio:

```bash
git clone https://github.com/simonsalassk8-svg/SIAPV-API.git
cd SIAPV-API
